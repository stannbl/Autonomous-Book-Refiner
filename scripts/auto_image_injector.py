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
        """Detects if a page is a Part Intro or TOC by checking future chapter density."""
        matches = 0
        for other_file in md_files:
            other_num = int(other_file[:2])
            if other_num > current_ch_num:
                title = other_file[3:-3].replace('_', ' ').lower()
                if fuzz.partial_ratio(title, page_text.lower()) > 80:
                    matches += 1
        return matches >= 1

    def find_chapter_starts(self, doc, md_files):
        """Anchors chapters to physical pages, skipping mini-TOCs."""
        pdf_mapping = []
        last_found = 0
        search_start = max(10, int(len(doc) * 0.03))

        print(f"--- ANCHORING CHAPTERS ---")
        for filename in md_files:
            ch_num = int(filename[:2])
            title = filename[3:-3].replace('_', ' ').lower()

            found_page = -1
            for p_idx in range(max(last_found, search_start), len(doc)):
                page_text = doc[p_idx].get_text().lower()
                if fuzz.partial_ratio(title, page_text) > self.threshold:
                    if self.is_toc_page(page_text, ch_num, md_files): continue
                    found_page = p_idx
                    break

            if found_page != -1:
                print(f"  ✓ Ch {ch_num} anchored to PDF Page {found_page + 1}")
                pdf_mapping.append({"num": ch_num, "file": filename, "start_page": found_page})
                last_found = found_page + 3

        for i in range(len(pdf_mapping)):
            pdf_mapping[i]["end_page"] = pdf_mapping[i + 1]["start_page"] if i + 1 < len(pdf_mapping) else len(doc)
        return pdf_mapping

    def extract_visual(self, page, bbox, fig_id):
        """Prioritizes SVG for vector visuals, falls back to PNG."""
        img_name = f"fig_{fig_id.replace('.', '_')}"

        if self.use_svg:
            try:
                svg_data = page.get_svg_image(matrix=fitz.Identity, clip=bbox)
                if "<path" in svg_data or "<text" in svg_data:
                    file_path = self.assets_dir / f"{img_name}.svg"
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(svg_data)
                    return f"assets/{img_name}.svg", "SVG"
            except Exception:
                pass

        pix = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72), clip=bbox + (-2, -2, 2, 2))
        file_path = self.assets_dir / f"{img_name}.png"
        pix.save(file_path)
        return f"assets/{img_name}.png", "PNG"

    def process(self):
        doc = fitz.open(self.pdf_path)
        md_files = sorted([f for f in os.listdir(self.md_dir) if f.endswith('.md') and f[0:1].isdigit()])
        mapping = self.find_chapter_starts(doc, md_files)
        fig_regex = re.compile(r'(?:Figure|Fig)\s*(\d+[\.\-]\d+)', re.IGNORECASE)

        print(f"\n--- EXTRACTING VISUALS ---")
        for item in mapping:
            with open(self.md_dir / item['file'], 'r', encoding='utf-8') as f:
                content = f.read()

            fig_hooks = {}
            for p_idx in range(item['start_page'], item['end_page']):
                page = doc[p_idx]
                matches = fig_regex.findall(page.get_text())
                if not matches: continue

                img_info = page.get_image_info()
                for fig_id in matches:
                    rects = page.search_for(f"Figure {fig_id}") or page.search_for(f"Fig. {fig_id}")
                    if not rects: continue
                    caption_y = (rects[0].y0 + rects[0].y1) / 2
                    best_bbox, min_dist = None, float('inf')
                    for img in img_info:
                        if img['width'] < 50: continue
                        img_bbox = fitz.Rect(img['bbox'])
                        dist = abs(caption_y - ((img_bbox.y0 + img_bbox.y1) / 2))
                        if img_bbox.y1 < caption_y: dist *= 0.6  # Image-above-caption bias
                        if dist < min_dist: min_dist, best_bbox = dist, img_bbox

                    if best_bbox:
                        rel_path, v_type = self.extract_visual(page, best_bbox, fig_id)
                        fig_hooks[fig_id] = rel_path
                        print(f"    {v_type} Found: Fig {fig_id} in {item['file']}")

            for fig_id, rel_path in fig_hooks.items():
                md_link = f"\n\n![Figure {fig_id}]({rel_path})\n\n"
                pattern = re.compile(rf'(?:Figure|Fig)\s*{re.escape(fig_id)}', re.IGNORECASE)
                if pattern.search(content):
                    content = pattern.sub(lambda m: f"{md_link}{m.group(0)}", content, count=1)

            with open(self.output_dir / item['file'], 'w', encoding='utf-8') as f:
                f.write(content)
        print(f"\nDone! Check {self.output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('pdf')
    parser.add_argument('md_dir')
    parser.add_argument('-o', '--out', default='rag_ready_book')
    parser.add_argument('--no-svg', action='store_false', dest='use_svg')
    args = parser.parse_args()
    AdvancedImageProcessor(args.pdf, args.md_dir, args.out, use_svg=args.use_svg).process()