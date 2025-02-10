import os
import re
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox
from openai import OpenAI

###############################################################################
# GLOBAL VARIABLES / CONSTANTS
###############################################################################
client = None  # We'll set this once the user enters their API key
API_KEY_FILENAME = "api_key.txt"
PROGRAMS_DIR = "programs"
ERROR_LOG_FILE = "error_log.txt"  # New constant for error logging

# Simple regex for lines like: "import X" or "from X import Y"
IMPORT_REGEX = re.compile(r'^\s*(?:from\s+([a-zA-Z0-9_]+)\s+import\s+.*|import\s+([a-zA-Z0-9_]+))')

# A small list of modules we do NOT prompt for, as they’re almost always installed or built-in
BLACKLISTED_IMPORTS = {"sys", "os", "re", "subprocess", "tkinter", "importlib"}

META_SYSTEM_PROMPT = """
You are an advanced AI that will generate a Python program, given specific user details.

Below are the user's details:
- Title: {user_title}
- Description: {user_description}
- Inputs: {user_inputs}
- Outputs: {user_outputs}

# Requirements
1. Produce a Python script that meets the user's requirements.
2. Return ONLY the Python code, wrapped in triple backticks.
3. Do NOT include any additional explanation outside the triple backticks.
4. When you provide the final code, ensure that if the program runs to completion without *known* errors, when the program is terminated/closed it exits with `sys.exit(0)`.
5. ALL SCRIPTS MUST BE GUI BASED ESPEICALLY IF THEY REQUIRE USER INPUT

# Additional Guidelines
- Code must be self-contained if possible.
- Respect user constraints as best as you can.
- Keep it concise and correct.

When responding, enclose the entire Python script between triple backticks (```) with no additional text.
""".strip()

###############################################################################
# HELPER FUNCTIONS
###############################################################################
def construct_meta_prompt(title: str, description: str, inputs: str, outputs: str) -> str:
    return META_SYSTEM_PROMPT.format(
        user_title=title,
        user_description=description,
        user_inputs=inputs,
        user_outputs=outputs
    )

def extract_code_from_response(response_text: str) -> str:
    """
    Extracts the first code block from triple backticks. If none, return entire text.
    """
    pattern = r"```(?:python)?(.*?)```"
    matches = re.findall(pattern, response_text, flags=re.DOTALL)
    if matches:
        return matches[0].strip()
    else:
        return response_text.strip()


def save_code_to_file(filename: str, code: str) -> str:
    """
    Saves code in programs/<filename>.py. Creates the 'programs' folder
    if needed, and returns the *absolute* path.
    """
    # 1) Convert 'programs' to absolute path
    abs_dir = os.path.abspath(PROGRAMS_DIR)

    # 2) Create the directory if it doesn't exist
    os.makedirs(abs_dir, exist_ok=True)

    # 3) Ensure filename ends with .py
    if not filename.lower().endswith(".py"):
        filename += ".py"

    # 4) Full path to the file
    final_path = os.path.join(abs_dir, filename)

    # 5) Write the file
    with open(final_path, "w", encoding="utf-8") as f:
        f.write(code)

    # 6) Return the absolute path
    return final_path

def load_api_key_from_file() -> str:
    """
    Load the API key from api_key.txt if present, else return empty string.
    """
    if os.path.exists(API_KEY_FILENAME):
        with open(API_KEY_FILENAME, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""

def save_api_key_locally(api_key: str) -> None:
    """
    Save the given API key into api_key.txt.
    """
    with open(API_KEY_FILENAME, "w", encoding="utf-8") as f:
        f.write(api_key.strip())

# Store logs in a directory called 'logs'
ERROR_LOG_FILE = "logs/error_log.txt"

def log_error(message: str):
    """Append an error message to the error log file. Create the file (and directory) if needed."""
    # Determine the directory portion of the path
    dir_name = os.path.dirname(ERROR_LOG_FILE)

    # Create the directory if it doesn't exist
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    
    # Open in append mode; this will create the file if it doesn't exist
    with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(message + "\n")

###############################################################################
# IMPORT PARSING & INSTALL LOGIC
###############################################################################
def parse_imports(code: str) -> set:
    """
    Naive approach: match lines with 'import X' or 'from X import Y'.
    Return a set of top-level package names.
    """
    found = set()
    for line in code.splitlines():
        match = IMPORT_REGEX.match(line)
        if match:
            pkg = match.group(1) or match.group(2)
            if pkg:
                # Only take top-level (e.g. 'requests' from 'requests.models')
                top = pkg.split('.')[0]
                found.add(top)
    return found

def install_or_upgrade_package(package: str):
    """
    Attempt to install or upgrade 'package' using 'pip install --upgrade <package>'.
    Parse the output; if we see 'Requirement already satisfied', 
    we tell the user it's already installed. Otherwise, we confirm success or show error.
    """
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", package]
    process = subprocess.run(cmd, capture_output=True, text=True)
    
    # Check the output
    if process.returncode == 0:
        stdout_lower = process.stdout.lower()
        if "requirement already satisfied" in stdout_lower:
            messagebox.showinfo(
                "Package Check",
                f"'{package}' is already installed (requirement already satisfied)."
            )
        else:
            messagebox.showinfo("Installation Success", f"Successfully installed/upgraded '{package}'.")
    else:
        messagebox.showerror(
            "Installation Failed",
            f"Failed to install/upgrade '{package}'.\n\n{process.stderr}"
        )

def maybe_install_dependencies(code: str):
    """
    Naively parse imports, for each import not in BLACKLISTED_IMPORTS,
    ask user if they want to run 'pip install --upgrade <package>'.
    """
    imports = parse_imports(code)
    if not imports:
        return  # no imports, nothing to do

    for pkg in imports:
        if pkg in BLACKLISTED_IMPORTS:
            # skip these as we assume they're standard or built-in
            continue

        answer = messagebox.askyesno(
            "Dependency Detected",
            f"This script imports '{pkg}'.\n\nInstall or upgrade '{pkg}' via pip now?"
        )
        if answer:
            install_or_upgrade_package(pkg)

###############################################################################
# GPT CALL
###############################################################################
def generate_program_code(title: str, description: str, inputs: str, outputs: str, error_context: str = "") -> str:
    """
    1) Build system prompt
    2) Send to model
    3) Extract code from triple backticks
    4) If an error happened before, provide context to GPT
    """
    if client is None:
        raise RuntimeError("API client not initialized. Please set your API key first.")

    system_prompt = construct_meta_prompt(title, description, inputs, outputs)
    
    if error_context:
        system_prompt += f"\n\nPrevious attempt failed with this error:\n{error_context}"

    try:
        response = client.chat.completions.create(
            model="o3-mini",
            reasoning_effort="medium",
            messages=[{"role": "system", "content": system_prompt}]
        )

        if not response or not response.choices or not response.choices[0].message.content:
            log_error("GPT response was empty or invalid.")
            raise RuntimeError("OpenAI API returned an empty response.")

        raw_output = response.choices[0].message.content
        return extract_code_from_response(raw_output)

    except Exception as e:
        log_error(f"GPT call failed: {e}")
        raise RuntimeError(f"OpenAI API call failed: {e}")

###############################################################################
# CLEAR PROGRAMS
###############################################################################
def delete_all_programs():
    if not os.path.isdir(PROGRAMS_DIR):
        messagebox.showinfo("Info", f"No '{PROGRAMS_DIR}' directory found.")
        return

    confirm = messagebox.askyesno(
        "Confirm Deletion",
        f"Are you sure you want to delete all files in '{PROGRAMS_DIR}'?"
    )
    if not confirm:
        return

    try:
        count_deleted = 0
        for filename in os.listdir(PROGRAMS_DIR):
            file_path = os.path.join(PROGRAMS_DIR, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
                count_deleted += 1

        messagebox.showinfo("Success", f"Deleted {count_deleted} file(s) from '{PROGRAMS_DIR}'.")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to delete programs:\n{e}")

def delete_program(filename: str):
    """
    Deletes a specific program file before retrying a new generation.
    """
    file_path = os.path.join(PROGRAMS_DIR, filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            log_error(f"Deleted program: {filename}")
        except Exception as e:
            log_error(f"Failed to delete {filename}: {e}")
            messagebox.showerror("Error", f"Failed to delete {filename}: {e}")

###############################################################################
# TKINTER GUI
###############################################################################
root = tk.Tk()
root.title("AI Python Program Generator")
root.geometry("700x650")

style = ttk.Style()
if "clam" in style.theme_names():
    style.theme_use("clam")

# Heading
top_frame = ttk.Frame(root, padding="10 10 10 0")
top_frame.pack(side=tk.TOP, fill=tk.X)

heading_label = ttk.Label(
    top_frame,
    text="AI Python Program Generator",
    font=("Helvetica", 16, "bold")
)
heading_label.pack(side=tk.LEFT, anchor="w")

# API Key Frame
api_frame = ttk.Labelframe(root, text="OpenAI API Key", padding="10 10 10 10")
api_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

api_key_label = ttk.Label(api_frame, text="Enter your API Key:")
api_key_label.grid(row=0, column=0, sticky="w")

entry_api_key = ttk.Entry(api_frame, width=58, show="*")
entry_api_key.grid(row=0, column=1, padx=5, pady=5, sticky="w")

# Load any saved key
loaded_key = load_api_key_from_file()
if loaded_key:
    entry_api_key.insert(0, loaded_key)

remember_var = tk.BooleanVar(value=bool(loaded_key))
remember_check = ttk.Checkbutton(api_frame, text="Remember my API key", variable=remember_var)
remember_check.grid(row=1, column=0, columnspan=2, sticky="w")

def set_api_key():
    global client
    user_key = entry_api_key.get().strip()
    if not user_key:
        messagebox.showerror("Error", "Please enter an API key.")
        return
    try:
        client = OpenAI(api_key=user_key)
        if remember_var.get():
            save_api_key_locally(user_key)
        else:
            if os.path.exists(API_KEY_FILENAME):
                os.remove(API_KEY_FILENAME)
        messagebox.showinfo("Success", "API Key set successfully!")
    except Exception as e:
        messagebox.showerror("Error", f"Could not set API key: {e}")

set_key_button = ttk.Button(api_frame, text="Set API Key", command=set_api_key)
set_key_button.grid(row=1, column=1, padx=5, pady=5, sticky="e")

# Program Details Frame
io_frame = ttk.Labelframe(root, text="Program Details", padding="10 10 10 10")
io_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)

label_title = ttk.Label(io_frame, text="Program Title:")
label_title.grid(row=0, column=0, sticky="w", padx=5, pady=(0,5))
entry_title = ttk.Entry(io_frame, width=60)
entry_title.grid(row=0, column=1, padx=5, pady=(0,5), sticky="w")

label_description = ttk.Label(io_frame, text="Program Description:")
label_description.grid(row=1, column=0, sticky="nw", padx=5, pady=(0,5))
text_description = tk.Text(io_frame, width=60, height=4)
text_description.grid(row=1, column=1, padx=5, pady=(0,5), sticky="w")

label_inputs = ttk.Label(io_frame, text="Inputs:")
label_inputs.grid(row=2, column=0, sticky="nw", padx=5, pady=(0,5))
text_inputs = tk.Text(io_frame, width=60, height=4)
text_inputs.grid(row=2, column=1, padx=5, pady=(0,5), sticky="w")

label_outputs = ttk.Label(io_frame, text="Outputs:")
label_outputs.grid(row=3, column=0, sticky="nw", padx=5, pady=(0,5))
text_outputs = tk.Text(io_frame, width=60, height=4)
text_outputs.grid(row=3, column=1, padx=5, pady=(0,5), sticky="w")

io_frame.columnconfigure(1, weight=1)

bottom_frame = ttk.Frame(root, padding="10 10 10 10")
bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)


def on_generate_button_click():
    """
    Handles the button click to generate a program, run it, and optionally retry dynamically if it fails.
    Only deletes the script if the user explicitly chooses to retry after an error.
    """
    title_val = entry_title.get().strip()
    desc_val = text_description.get("1.0", tk.END).strip()
    inputs_val = text_inputs.get("1.0", tk.END).strip()
    outputs_val = text_outputs.get("1.0", tk.END).strip()

    if not title_val:
        messagebox.showerror("Error", "Please provide a Program Title.")
        return

    error_context = ""  # This will store error messages for GPT if we retry

    while True:
        try:
            # 1) Generate code (using GPT, possibly with error context)
            code = generate_program_code(title_val, desc_val, inputs_val, outputs_val, error_context)
            maybe_install_dependencies(code=code)

            # 2) Save the code
            final_path = save_code_to_file(title_val, code)
            messagebox.showinfo("Success", f"Program generated and saved as:\n{final_path}")
            script_dir = os.path.dirname(final_path)
            # 3) Run the generated script
            run_result = subprocess.run([sys.executable, final_path], capture_output=True, text=True, cwd=script_dir)

            # 4) Check success/failure
            if run_result.returncode == 0:
                # -- Success --
                out_msg = run_result.stdout.strip() or "(No output)"
                messagebox.showinfo(
                    "Program Output",
                    f"Program finished execution.\n\nOutput:\n{out_msg}"
                )
                # Exit the loop on success
                break
            else:
                # -- Failure --
                error_context = run_result.stderr.strip() or "(No error message)"
                log_error(f"Error in '{title_val}': {error_context}")
                messagebox.showerror(
                    "Program Error",
                    f"Program exited with an error.\n\nDetails:\n{error_context}"
                )

                # Ask user whether to retry (and thus re-generate)
                retry = messagebox.askyesno(
                    "Retry Generation?",
                    "Do you want to delete this failing script and regenerate a new one?"
                )
                if retry:
                    # 4A) Delete only if we're going to retry
                    delete_program(title_val)
                    messagebox.showinfo("Retrying", "The program encountered an error and will be regenerated.")
                    # Loop continues => new GPT generation
                else:
                    # 4B) Do NOT delete the file; just exit the loop
                    break

        except Exception as ex:
            messagebox.showerror("Error", str(ex))
            log_error(f"Unexpected failure: {ex}")
            # Exit the loop if there's an unexpected exception (like network/API failure)
            break


generate_button = ttk.Button(bottom_frame, text="Generate Program", command=on_generate_button_click)
generate_button.pack(side=tk.RIGHT, padx=5)

clear_button = ttk.Button(bottom_frame, text="Delete All Programs", command=delete_all_programs)
clear_button.pack(side=tk.LEFT, padx=5)

###############################################################################
# DEPENDENCY INSTALLATION LOGIC (UPGRADE)
###############################################################################

# Example partial set of standard-library modules to skip installation
STANDARD_LIBS = {
    "abc", "argparse", "asyncio", "base64", "bz2", "calendar", "collections",
    "concurrent", "contextlib", "copy", "csv", "datetime", "decimal", "enum",
    "functools", "glob", "hashlib", "heapq", "hmac", "http", "importlib",
    "io", "itertools", "json", "logging", "math", "numbers", "operator",
    "os", "pathlib", "pickle", "platform", "plistlib", "pprint", "queue",
    "random", "re", "selectors", "shutil", "signal", "socket", "sqlite3",
    "ssl", "stat", "string", "struct", "subprocess", "sys", "tempfile",
    "time", "tkinter", "traceback", "typing", "unittest", "urllib", "uuid",
    "xml", "zlib"
}

def is_standard_library(package_name: str) -> bool:
    """
    Checks if 'package_name' is recognized as part of the Python standard library.
    You can expand or refine this set as needed.
    """
    return package_name.lower() in STANDARD_LIBS

def maybe_install_dependencies(code: str):
    """
    Parses 'import X' lines, skipping blacklisted or standard library modules.
    Automatically installs missing packages without asking the user.
    If installation fails, logs the error and moves to the next package.
    """
    imports_found = parse_imports(code)  # <-- This should be defined in your HELPER FUNCTIONS
    if not imports_found:
        return

    for pkg in imports_found:
        # Skip blacklisted and standard library modules
        if pkg in BLACKLISTED_IMPORTS or is_standard_library(pkg):
            continue

        install_or_upgrade_package(pkg)  # Install package automatically

def install_or_upgrade_package(package: str):
    """
    Attempts to install or upgrade a package using 'pip install --upgrade <package>'.
    - If successful, logs success.
    - If it fails, logs the failure and continues without stopping execution.
    """
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", package]
    process = subprocess.run(cmd, capture_output=True, text=True)

    if process.returncode == 0:
        stdout_lower = process.stdout.lower()
        if "requirement already satisfied" in stdout_lower:
            log_error(f"'{package}' is already installed.")
        else:
            log_error(f"Successfully installed/upgraded '{package}'.")
    else:
        log_error(f"Failed to install '{package}': {process.stderr.strip()}")


###############################################################################
# START GUI LOOP
###############################################################################
root.mainloop()
