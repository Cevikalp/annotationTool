# Build Instructions for Annotation Tool

This guide covers the setup, configuration, and compilation of the Annotation Tool into a standalone executable. The tool is built using **Python 3**, **PySide6** (Qt), and **Ultralytics YOLO** for AI assistance.

## 1. Prerequisites

Ensure you have the following installed on your system:
* **Python 3.9 - 3.12** (Python 3.11 is recommended for best stability with PyInstaller).
* **Git** (to clone the repository).
* **pip** (Python package manager).

## 2. Project Setup

### Clone the Repository
```bash
git clone <your-repo-url>
cd annotationTool
```

### Create a Virtual Environment (Recommended)
It is highly recommended to use a clean virtual environment to keep the executable size optimized.

**Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate
```

### Install Dependencies
Install all required libraries, including PySide6, Ultralytics, and PyInstaller.

```bash
pip install --upgrade pip
pip install PySide6 ultralytics pyinstaller
```

---

## 3. Prepare Model & Resources

Before building, you must ensure the AI model and configuration files are present in the project folder.

1.  **Configuration Files:** Ensure `id_list.txt` and `yolo_config.json` are in the root directory.
2.  **Model Folder:** Create a `models` directory if it doesn't exist.
    ```bash
    mkdir models
    ```
3.  **Download Model:** Download the YOLO model (e.g., `yolo11n.pt`) and place it inside the `models/` folder.
    * *Option A (Auto-Download):* Run the python script once (`python annotation.py`); it will download the model to the root. Move it to `models/`.
    * *Option B (Manual Command):*
        ```bash
        yolo export model=yolo11n.pt format=torchscript
        mv yolo11n.pt models/
        ```

**Your folder structure should look like this:**
```text
annotationTool/
├── models/
│   └── yolo11n.pt
├── annotation.py
├── id_list.txt
├── yolo_config.json
└── ...
```

---

## 4. Build the Executable

We use **PyInstaller** to bundle the application. Select the command for your operating system.

### Option A: Linux & macOS
On Unix-based systems, use a **colon (`:`)** to separate source and destination paths.

```bash
pyinstaller --noconsole --onedir \
    --contents-directory "libs" \
    --add-data "id_list.txt:." \
    --add-data "yolo_config.json:." \
    --add-data "models/yolo11n.pt:models" \
    --hidden-import="ultralytics" \
    --name="AnnotationTool_v1" \
    annotation.py
```

### Option B: Windows (command prompt)
On Windows, use a **semicolon (`;`)** to separate source and destination paths.

```bash
pyinstaller --noconsole --onedir ^
    --contents-directory "libs" ^
    --add-data "id_list.txt;." ^
    --add-data "yolo_config.json;." ^
    --add-data "models/yolo11n.pt;models" ^
    --hidden-import="ultralytics" ^
    --name="AnnotationTool_v1" ^
    annotation.py
```

### Option C: Windows (Powershell)
On Windows, use a **semicolon (`;`)** to separate source and destination paths.

```bash
pyinstaller --noconsole --onedir `
    --contents-directory "libs" `
    --add-data "id_list.txt;." `
    --add-data "yolo_config.json;." `
    --add-data "models/yolo11n.pt;models" `
    --hidden-import="ultralytics" `
    --name="AnnotationTool_v1" `
    annotation.py
```


*(Note: If running in Command Prompt instead of PowerShell, remove the `^` line breaks and run as a single line).*

---

## 5. Locate & Run

Once the build finishes, your standalone executable will be located in the **`dist/`** folder.

* **Linux/Mac:** `dist/AnnotationTool_Linux`
* **Windows:** `dist/AnnotationTool_Win.exe`

You can now move this single file to any other machine. It does **not** require Python or PyTorch to be installed on the target machine.

### Troubleshooting

* **"Model not found" error:** Ensure `yolo_config.json` points to `"model_path": "models/yolo11n.pt"`.
* **File Size:** The executable will be large (~150MB - 300MB) because it bundles the PyTorch inference engine. This is normal.
* **GLIBC Error (Linux):** If you compile on a new Ubuntu version and try to run on an old one, it may fail. Always compile on the oldest OS version you intend to support (or use Docker).