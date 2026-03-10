<p align="center">

<img src="https://img.shields.io/badge/python-3.11+-black?style=for-the-badge&logo=python&logoColor=white">
<img src="https://img.shields.io/badge/PyQt6-GUI-black?style=for-the-badge&logo=qt&logoColor=white">
<img src="https://img.shields.io/badge/NumPy-ML%20Engine-black?style=for-the-badge&logo=numpy&logoColor=white">
<img src="https://img.shields.io/badge/License-MIT-black?style=for-the-badge">

</p>

<h1 align="center" style="font-size:60px;">Qnumber</h1>

<p align="center">
<img src="assets/screenshot.png" width="900">
</p>

### Qnumber

Qnumber is a desktop application for creating, managing, and training handwritten digit datasets with a fully interactive visual workflow.

It is designed as both:

- an educational tool for understanding how neural networks work internally
- a practical desktop environment for preparing 32×32 digit datasets, training a custom model, and testing predictions

The project combines a custom PyQt6 interface with a lightweight NumPy-based neural network engine. The goal is not to hide the mechanics behind abstraction, but to make the full pipeline visible: drawing, dataset preparation, training, inference, and inspection.

---

## Features

### Dataset creation
- Draw 32×32 digit images manually
- Create training and test samples
- Support for multiple visual formats and controlled experiments
- Fast sample generation workflow
- Reindex dataset files consistently

### Dataset management
- Built-in dataset gallery
- Train and test split organization
- Sorting and browsing tools
- Delete-all actions with confirmation
- Clear file naming workflow for large datasets

### Training
- Custom feed-forward neural network engine built with NumPy
- Configurable dense architectures such as:
  - `1024 → 128 → 64 → 10`
  - `1024 → 64 → 10`
- Real training workflow instead of black-box wrappers
- Educational visibility into the pipeline

### Testing and inference
- Run predictions on custom samples
- Inspect model output behavior
- Useful for understanding classification confidence and failure cases

### Interface
- Desktop UI built with PyQt6
- Modular page-based structure
- Designed for a dark, high-contrast workflow
- Built for direct experimentation rather than notebook-only usage

---

## Project Philosophy

Most beginner ML tools abstract away too much. Qnumber does the opposite.

This project is built to let the user see the actual structure of a small neural network system:

1. create or collect image data
2. organize the dataset
3. train a model
4. test the model
5. inspect what happens

That makes Qnumber useful not only as a utility, but as a learning instrument for machine learning fundamentals.

---

## Installation

Clone the repository:

```bash
git clone https://github.com/milord-x/Qnumber.git
cd Qnumber

Create a virtual environment:

Bash / Zsh
python3 -m venv .venv
source .venv/bin/activate

Fish
python3 -m venv .venv
source .venv/bin/activate.fish

Install dependencies:

pip install -r requirements.txt

Run the application:
python3 app.py
```

---

## Requirements

| №  | library     | Version |
|----|-------------|---------|
| 1  | Python      | >=3.11+ |
| 2  | PyQt6       | >=6.6   |
| 3  | numpy       | >=1.26  |
| 4  | Pillow      | >=10.0  |
| 5  | matplotlib  | >=3.8   |

---

## Project Structure

```bash
Qnumber/
├── app.py
├── requirements.txt
├── assets/
│   └── archive/
├── dataset/
│   ├── train/
│   └── test/
├── ui/
│   ├── main_window.py
│   ├── pages/
│   └── widgets/
├── LICENSE
└── README.md
```
