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
2.  **App Icon:** Place an .ico file named NeuroTag.ico in the root directory.
3.  **Model Folder:** Create a `models` directory if it doesn't exist.
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
├── NeuroTag.ico
└── ...
```

---

## 4. Build the Executable

We use **PyInstaller** to bundle the application. We use the --onedir mode to create a folder containing the executable and its libraries (more stable than a single file).

**Select the command for your operating system:**

### Option A: Linux & macOS
On Unix-based systems, use a **colon (`:`)** to separate source and destination paths.

```bash
pyinstaller --noconsole --onedir \
    --contents-directory "libs" \
    --add-data "id_list.txt:." \
    --add-data "yolo_config.json:." \
    --add-data "models/yolo11n.pt:models" \
    --add-data "NeuroTag.ico:." \
    --hidden-import="ultralytics" \
    --icon "NeuroTag.ico" \
    --distpath "Final_Build" \
    --name="NeuroTag" \
    annotation.py
```
*use .icns instead of .ico when on mac*

### Option B: Windows (command prompt)
On Windows, use a **semicolon (`;`)** to separate source and destination paths.

```bash
pyinstaller --noconsole --onedir ^
    --contents-directory "libs" ^
    --add-data "id_list.txt;." ^
    --add-data "yolo_config.json;." ^
    --add-data "models/yolo11n.pt;models" ^
    --add-data "NeuroTag.ico;." ^
    --hidden-import="ultralytics" ^
    --icon "NeuroTag.ico" ^
    --distpath "Final_Build" ^
    --name="NeuroTag" ^
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
    --add-data "NeuroTag.ico;." `
    --hidden-import="ultralytics" `
    --icon "NeuroTag.ico" `
    --distpath "Final_Build" `
    --name="NeuroTag" `
    annotation.py
```


*(Note: If running in Command Prompt instead of PowerShell, remove the `^` line breaks and run as a single line).*

---

## 5. Locate & Run

Once the build finishes, your standalone application will be located in the Final_Build/ folder.
For Distribution (Important)

Since we used --onedir, the output is a Folder, not a single file.

1.    Navigate to Final_Build/.

2.   Find the folder named NeuroTag.

3.   Zip this entire folder (e.g., named NeuroTag_Student_v1.zip).

4.    Distribute the Zip file.

*Warning: Do not move the .exe file out of this folder. It requires the libs folder next to it to function.*

### Troubleshooting

* **"Model not found" error:** Ensure `yolo_config.json` points to `"model_path": "models/yolo11n.pt"`.
* **File Size:** The executable will be large (~150MB - 300MB) because it bundles the PyTorch inference engine. This is normal.
* **GLIBC Error (Linux):** If you compile on a new Ubuntu version and try to run on an old one, it may fail. Always compile on the oldest OS version you intend to support (or use Docker).