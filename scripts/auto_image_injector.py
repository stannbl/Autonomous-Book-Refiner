import fitz
import re
import os
import argparse
from pathlib import Path
from thefuzz import fuzz


class AdvancedImageProcessor:
    def __init__(self, pdf_path, md_dir, output_dir, use_svg=True, threshold=85):
        self.pdf_path = Path(pdf_path)
        self.md_dir = Path(md_dir)
        self.output_dir = Path(output_dir)
        self.use_svg = use_svg
        self.threshold = threshold
        self.assets_dir = self.output_dir / "assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def is_toc_page(self, page_text, current_ch_num, md_files):
        matches = 0
        for other_file in md_files:
            other_num = int(other_file[:2])
            if other_num > current_ch_num:
                title = other_file[3:-3].replace('_', ' ').lower()
                if fuzz.partial_ratio(title, page_text.lower()) > 80:
                    matches += 1
        return matches >= 1

    def find_chapter_starts(self, doc, md_files):
        pdf_mapping = []
        last_found = 0
        search_start = max(10, int(len(doc) * 0.03))
        for filename in md_files:
            ch_num = int(filename[:2])
            title = filename[3:-3].replace('_', ' ').lower()
            found_page = -1
            for p_idx in range(max(last_found, search_start), len(doc)):
                if fuzz.partial_ratio(title, doc[p_idx].get_text().lower()) > self.threshold:
                    if self.is_toc_page(doc[p_idx].get_text(), ch_num, md_files): continue
                    found_page = p_idx
                    break
            if found_page != -1:
                pdf_mapping.append({"num": ch_num, "file": filename, "start_page": found_page})
                last_found = found_page + 3
        for i in range(len(pdf_mapping)):
            pdf_mapping[i]["end_page"] = pdf_mapping[i + 1]["start_page"] if i + 1 < len(pdf_mapping) else len(doc)
        return pdf_mapping

    def get_vector_clusters(self, page):
        """Groups vector paths with aggressive flowchart bridging."""
        paths = page.get_drawings()
        clusters = []
        for p in paths:
            r = fitz.Rect(p["rect"])
            if r.width < 5 or r.height < 5: continue
            merged = False
            for i, c_rect in enumerate(clusters):
                # 50pt bridge for complex diagrams like Fig 5.6
                if r.intersects(fitz.Rect(c_rect.x0 - 50, c_rect.y0 - 50, c_rect.x1 + 50, c_rect.y1 + 50)):
                    clusters[i] = c_rect | r
                    merged = True
                    break
            if not merged: clusters.append(r)
        return [c for c in clusters if c.width > 60 and c.height > 40]

    def extract_visual(self, page, bbox, fig_id):
        img_name = f"fig_{fig_id.replace('.', '_')}"
        if self.use_svg:
            try:
                svg_data = page.get_svg_image(matrix=fitz.Identity, clip=bbox)
                if "<path" in svg_data or "<text" in svg_data:
                    with open(self.assets_dir / f"{img_name}.svg", "w") as f: f.write(svg_data)
                    return f"assets/{img_name}.svg", "SVG"
            except:
                pass
        pix = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72), clip=bbox + (-2, -2, 2, 2))
        pix.save(self.assets_dir / f"{img_name}.png")
        return f"assets/{img_name}.png", "PNG"

    def process(self):
        doc = fitz.open(self.pdf_path)
        md_files = sorted([f for f in os.listdir(self.md_dir) if f.endswith('.md') and f[0:1].isdigit()])
        mapping = self.find_chapter_starts(doc, md_files)
        fig_regex = re.compile(r'(?:Figure|Fig)\s*(\d+[\.\-]\d+)', re.IGNORECASE)

        print(f"\n--- EXTRACTING VISUALS (GEOMETRIC REJECTION) ---")
        for item in mapping:
            with open(self.md_dir / item['file'], 'r') as f:
                content = f.read()
            fig_hooks = {}
            for p_idx in range(item['start_page'], item['end_page']):
                page = doc[p_idx]
                matches = list(fig_regex.finditer(page.get_text()))

                candidates = []
                max_area = 1
                for img in page.get_image_info():
                    r = fitz.Rect(img['bbox'])
                    # GEOMETRIC FILTER: If height < 15, it's a watermark line, not a figure.
                    if r.height < 15: continue
                    candidates.append({'bbox': r, 'type': 'raster', 'area': r.get_area()})
                    max_area = max(max_area, r.get_area())
                for v in self.get_vector_clusters(page):
                    candidates.append({'bbox': v, 'type': 'vector', 'area': v.get_area()})
                    max_area = max(max_area, v.get_area())

                for match in matches:
                    fig_id = match.group(1)
                    rects = page.search_for(match.group(0))
                    if not rects: continue
                    cap_y, cap_x = (rects[0].y0 + rects[0].y1) / 2, (rects[0].x0 + rects[0].x1) / 2

                    best_bbox, min_score = None, float('inf')
                    for cand in candidates:
                        bbox = cand['bbox']
                        score = abs(cap_y - (bbox.y0 + bbox.y1) / 2) + (abs(cap_x - (bbox.x0 + bbox.x1) / 2) * 0.4)
                        if bbox.y1 < cap_y: score *= 0.5
                        # Aggressive penalty for tiny objects relative to the page's largest item
                        if cand['area'] < (max_area * 0.15): score *= 100.0
                        if score < min_score: min_score, best_bbox = score, bbox

                    if best_bbox:
                        path, v_type = self.extract_visual(page, best_bbox, fig_id)
                        fig_hooks[fig_id] = path
                        print(f"  ✓ {v_type} Fig {fig_id} in {item['file']}")

            # Fixed SyntaxWarning: Use a non-f-string for the replacement group
            for fid, path in fig_hooks.items():
                replacement = f"\n\n![Figure {fid}]({path})\n\n" + r"\g<0>"
                content = re.sub(rf'(?:Figure|Fig)\s*{re.escape(fid)}', replacement, content, count=1)

            with open(self.output_dir / item['file'], 'w') as f:
                f.write(content)
        print("✅ Success.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('pdf');
    parser.add_argument('md_dir');
    parser.add_argument('-o', '--out', default='rag_output')
    args = parser.parse_args();
    AdvancedImageProcessor(args.pdf, args.md_dir, args.out).process()