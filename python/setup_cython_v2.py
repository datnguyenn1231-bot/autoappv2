"""
AuraSplit v2 — Cython Build Script
Compiles Python files in resources/python/ to .pyd for code protection.
Run from AuraSplit_v2/python/ directory.
"""
import os
import sys
import shutil
from setuptools import setup, Extension
from Cython.Build import cythonize

# Files to compile to .pyd
FILES_TO_PROTECT = [
    "process_task.py",
    "api_wrapper.py",
    "model_checker.py",
    "config/paths.py",
    "_seq.py",
]

# Files that MUST stay .py (crash in .pyd — proven in V1)
# - sk1_cutting.py: subprocess + import torch/whisperx
# - sk3_image_flow.py: subprocess + import torch/whisperx  
# - safe_kernel.py: FFmpeg subprocess.Popen crash
FILES_KEEP_PY = [
    "engines/sk1_cutting.py",
    "engines/sk3_image_flow.py",
    "safe_kernel.py",
]

def main():
    # Filter to only existing files
    extensions = []
    for f in FILES_TO_PROTECT:
        if os.path.isfile(f):
            # Module name = file path without .py, with / replaced by .
            mod_name = f.replace("/", ".").replace("\\", ".").replace(".py", "")
            extensions.append(Extension(mod_name, [f]))
            print(f"  [QUEUE] {f} -> {mod_name}.pyd")
        else:
            print(f"  [SKIP] {f} not found")
    
    if not extensions:
        print("ERROR: No files to compile!")
        sys.exit(1)
    
    print(f"\nCompiling {len(extensions)} files with Cython...")
    
    setup(
        ext_modules=cythonize(
            extensions,
            compiler_directives={
                'language_level': '3',
                'boundscheck': False,
                'wraparound': False,
            },
            force=True,
        ),
        script_args=['build_ext', '--inplace'],
    )
    
    print("\n✅ Cython compilation complete!")
    
    # List generated .pyd files
    for root, dirs, files in os.walk("."):
        for f in files:
            if f.endswith(".pyd"):
                path = os.path.join(root, f)
                size_kb = os.path.getsize(path) / 1024
                print(f"  [PYD] {path} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
