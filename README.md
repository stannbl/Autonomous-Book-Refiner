# Autonomous-Book-Refiner

**Autonomous-Book-Refiner** is a robust post-processing pipeline designed to transform raw, unstructured Markdown (generated via tools like **Docling** or **Marker**) into high-fidelity, chapter-stratified "skills" for LLMs.

It solves the two biggest hurdles in document digitization: resolving malformed Tables of Contents and precisely synchronizing physical PDF assets (images/vectors) with semantic text anchors.

## 💡 Key Features

### 1. Election-Based MD Splitting

Standard splitters often fail when a Table of Contents is poorly parsed or contains noisy descriptions. This tool performs a global scan to discover potential "chapter clusters" and uses an **Election Logic** to identify and follow the most complete and sequential chapter list.

### 2. Density-Aware Sequential Mapping

To avoid getting "stuck" on Part Intro or Mini-TOC pages that list multiple chapters at once, the pipeline uses a **Sequential Matcher**. It verifies the start of a chapter by analyzing the density of titles on a page, ensuring images are mapped to the actual body text rather than summary pages.

### 3. Spatial Proximity Figure Extraction

The system scans the PDF for figure captions (e.g., "Figure 1.1") and performs a spatial proximity search. By applying an **above-caption bias**, it accurately extracts the correct visual asset even in dense textbook layouts where multiple images share a single page.

### 4. Hybrid Vector/Raster Support

The pipeline prioritizes **SVG extraction** for architectural diagrams and system schemas, preserving searchable text labels for RAG indexing. It automatically falls back to high-DPI **PNG snapshots** for photographs or flattened raster images.

## 🛠 Installation

1. **Clone the repository:**
```bash
git clone https://github.com/stannbl/Autonomous-Book-Refiner.git
cd Autonomous-Book-Refiner

```


2. **Install dependencies:**
```bash
pip install -r requirements.txt

```



## 🚀 Usage

The pipeline consists of two primary steps:

### Step 1: Split the Markdown

Pass your raw Markdown (e.g., from Docling) to refine the chapters and titles.

```bash
python scripts/splitter_improved_v3.py "path/to/raw_book.md" -o chapters/

```

### Step 2: Inject Assets

Point the injector to your source PDF and the split chapters. It will map the pages and inject images/vectors directly into the Markdown files.

```bash
python scripts/auto_image_injector.py "path/to/book.pdf" chapters/ -o final_output/

```

## 📂 Project Structure

* `scripts/splitter_improved_v3.py`: The Election-based logic for chapter stratification.
* `scripts/auto_image_injector.py`: The Sequential Mapper and Figure Extractor.
* `requirements.txt`: Standard Python dependencies.
