#!/usr/bin/env python3
import re
import argparse
from pathlib import Path
from thefuzz import fuzz


class ChapterCandidate:
    def __init__(self, num, hint, line_idx, raw_text):
        self.num = num
        self.hint = hint
        self.line_idx = line_idx
        self.raw_text = raw_text


class ElectionRefinedSplitter:
    def __init__(self, input_file, output_dir, toc_gap=10, threshold=85):
        self.input_file = Path(input_file)
        self.output_dir = Path(output_dir)
        self.toc_gap = toc_gap
        self.threshold = threshold
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_name_len = 80

    def sanitize_filename(self, name):
        """Standardizes names and enforces a safe length."""
        clean = re.sub(r'[^a-zA-Z0-9]+', '_', name)
        clean = re.sub(r'_+', '_', clean).strip('_')
        return clean[:self.max_name_len]

    def find_all_toc_clusters(self, lines):
        """Finds all potential chapter lists in the document."""
        clusters = []
        current_cluster = []
        last_line_idx = -1

        for i, line in enumerate(lines):
            clean = line.strip()
            # Match "Chapter 1", "Chapter 01"
            match = re.search(r'Chapter\s+(\d+)[:\-\s,]+(.*)', clean, re.IGNORECASE)

            if match:
                num = int(match.group(1))
                hint = re.sub(r'[\s.]+ \d+$', '', match.group(2).strip())
                candidate = ChapterCandidate(num, hint, i, clean)

                if last_line_idx != -1 and (i - last_line_idx) > self.toc_gap:
                    if current_cluster:
                        clusters.append(current_cluster)
                    current_cluster = []

                current_cluster.append(candidate)
                last_line_idx = i

        if current_cluster:
            clusters.append(current_cluster)
        return clusters

    def elect_best_cluster(self, clusters):
        """Selects the vector that is longest and correctly ordered."""
        if not clusters: return None
        scored = []
        for cluster in clusters:
            length = len(cluster)
            seq = sum(2 for i in range(len(cluster) - 1) if cluster[i + 1].num == cluster[i].num + 1)
            scored.append((length + seq, cluster))
        return sorted(scored, key=lambda x: x[0], reverse=True)[0][1]

    def refine_title(self, body_line, target_num):
        """
        REFINEMENT LOGIC: Extracts the actual title from the body header.
        Removes 'Chapter X' and cleaning symbols to get just the name.
        """
        # Remove MD headers and Chapter markers
        clean = re.sub(r'^[#\s*]+', '', body_line).strip()
        clean = re.sub(rf'^Chapter\s+{target_num}[:\-\s,]*', '', clean, flags=re.IGNORECASE).strip()

        # If the result is too short or just punctuation, it failed
        if len(clean) < 3: return None

        # Split by common description separators (like the commas in your TOC)
        # to try and get just the title part if a summary is attached
        if ' , ' in clean:
            clean = clean.split(' , ')[0]

        return clean.strip()

    def run(self):
        with open(self.input_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        true_toc = self.elect_best_cluster(self.find_all_toc_clusters(lines))
        if not true_toc:
            print("No valid TOC sequence found.")
            return

        print(f"--- ELECTED TOC (Line {true_toc[0].line_idx + 1}) ---")
        search_start_line = true_toc[-1].line_idx + 1
        split_points = [(0, "00_Front_Matter.md")]
        expected_ptr = 0

        print(f"\n--- SCANNING BODY (Starting line {search_start_line}) ---")

        for i in range(search_start_line, len(lines)):
            if expected_ptr >= len(true_toc): break

            target = true_toc[expected_ptr]
            line = lines[i]
            clean = line.strip()

            is_match = False
            if re.match(rf'^#+\s*Chapter\s+{target.num}\b', clean, re.IGNORECASE):
                is_match = True
            elif clean.startswith('#'):
                clean_text = re.sub(r'^[#\s*]+', '', clean).strip()
                if fuzz.partial_ratio(target.hint.lower(), clean_text.lower()) >= self.threshold:
                    is_match = True

            if is_match:
                # --- REFINEMENT STEP ---
                refined = self.refine_title(line, target.num)
                # Use refined title if found, otherwise fallback to sanitized TOC hint
                title_for_file = refined if refined else target.hint

                safe_name = self.sanitize_filename(title_for_file)
                filename = f"{target.num:02d}_{safe_name}.md"

                print(f"  ✓ Found Ch {target.num} (Line {i + 1}) -> Refined to: '{title_for_file[:40]}...'")
                split_points.append((i, filename))
                expected_ptr += 1

        print(f"\n--- SAVING {len(split_points)} FILES ---")
        for i in range(len(split_points)):
            start, fname = split_points[i]
            end = split_points[i + 1][0] if i + 1 < len(split_points) else len(lines)
            with open(self.output_dir / fname, 'w', encoding='utf-8') as out:
                out.writelines(lines[start:end])
            print(f"  Saved: {fname}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('input')
    parser.add_argument('-o', '--out', default='chapters')
    args = parser.parse_args()
    ElectionRefinedSplitter(args.input, args.out).run()