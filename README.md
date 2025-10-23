# LaTeX Acronym Inspector

A Python tool that analyzes LaTeX documents for inconsistent acronym usage and generates a PDF report.

⚠️ **Preliminary Version** - This is an early version. Expect bugs and missing features! Please contribute improvements or suggest features you'd like to see.

**Credits**: All coding by Claude AI. I just wanted a tool to check my LaTeX acronyms.

## What It Detects

- **Informal definitions**: Acronyms appear in parentheses multiple times but are not formally defined in glossaries.
- **Inconsistent usage**: Acronyms are properly defined in glossaries but their full forms are also used in the text instead of using /gls or /glspl.


## Installation

```bash
git clone https://github.com/YuchenZHANG2/latex-acronym-inspector.git
cd latex-acronym-inspector
pip install -r requirements.txt
```


## Sample Project

Test with the included sample:
```bash
python test_analyzer.py
```



## Usage

1. Edit configuration in `analyze_acronyms.py`:
   ```python
   ENTRY_FILE = "main.tex"        # Your main LaTeX file
   ROOT_DIR = "./your_project"    # Path to your project
   OUTPUT_NAME = "output_sample.pdf" # Name of the output PDF
   ```

2. Run:
   ```bash
   python analyze_acronyms.py
   ```



