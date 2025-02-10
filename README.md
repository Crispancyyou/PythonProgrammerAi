# AI Python Program Generator

An interactive GUI tool that uses OpenAI's GPT API to generate Python programs based on your specifications. The tool not only generates the code but also automatically manages dependencies and runs the generated script—all from a simple Tkinter interface.

> **Note:** This project is currently in **beta** and serves as a proof of concept. It is expected to evolve with additional features and improvements over time.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Directory Structure](#directory-structure)
- [How It Works](#how-it-works)
- [Customization](#customization)
- [Troubleshooting & Logs](#troubleshooting--logs)
- [Contributing](#contributing)
- [Disclaimer](#disclaimer)
- [License](#license)

## Overview

The **AI Python Program Generator** is designed to help you generate Python scripts using natural language descriptions. Simply provide the title, description, inputs, and outputs of the desired program, and the tool leverages an OpenAI GPT model to produce a complete, runnable Python script. The generated program is automatically saved in a designated folder, its dependencies are managed automatically, and it is executed with real-time feedback. If errors occur during execution, you can choose to regenerate the program with the error context passed back to the model for refinement.

## Features

- **Graphical User Interface (GUI):** Built using Tkinter for a simple and user-friendly experience.
- **API Key Management:** Enter and optionally save your OpenAI API key locally.
- **Dynamic Code Generation:** Constructs a detailed meta prompt from your program details and sends it to the GPT model.
- **Code Extraction:** Extracts Python code (enclosed in triple backticks) from the GPT response.
- **Automatic Dependency Installation:** Scans the generated code for import statements and installs any missing packages using pip.
- **Execution & Error Handling:** Runs the generated script, captures output and errors, and offers an option to regenerate the program if errors occur.
- **Program Management:** Saves generated scripts to a dedicated `programs/` directory and provides an option to delete all programs.

## Requirements

Before using this tool, ensure you meet the following prerequisites:

- **Python Pre-installed:**  
  You must have Python version **3.6** or later installed on your system. The tool relies on Python's standard libraries (such as `os`, `re`, `sys`, and `subprocess`) and the Tkinter module (typically included with Python installations).

- **OpenAI API Key:**  
  A valid OpenAI API key is required for generating Python programs via the GPT model. You can obtain an API key by signing up at [OpenAI's website](https://openai.com/). The API key must be entered into the GUI when prompted.

- **Internet Connectivity:**  
  Since the tool communicates with the OpenAI API, a stable internet connection is necessary.

- **Pip (Python Package Installer):**  
  Ensure pip is installed and accessible from your command line to handle dependency installations automatically.

## Installation

1. **Clone or Download the Repository:**

   ```bash
   git clone https://github.com/yourusername/ai-python-program-generator.git
   cd ai-python-program-generator
