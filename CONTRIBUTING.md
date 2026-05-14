# Contributing to AI Audit Shelf

First off, thank you for considering contributing to AI Audit Shelf! It's people like you that make the open-source community such a great place to learn, inspire, and create.

We welcome all types of contributions: bug reports, feature requests, documentation improvements, and code contributions.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [How to Contribute](#how-to-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Enhancements](#suggesting-enhancements)
  - [Pull Requests](#pull-requests)
- [Local Development Setup](#local-development-setup)
- [Styleguides](#styleguides)

## Code of Conduct

By participating in this project, you are expected to uphold our code of conduct. Please be respectful and welcoming to all contributors.

## Getting Started

1. Check the [issue tracker](https://github.com/ATHARVA262005/ai-audit-shelf/issues) to see if your issue or feature has already been reported or requested.
2. If you are a beginner, look for issues labeled [`good first issue`](https://github.com/ATHARVA262005/ai-audit-shelf/labels/good%20first%20issue). These are a great way to get familiar with the codebase!

## How to Contribute

### Reporting Bugs

If you find a bug, please use the **Bug Report** template when opening an issue. Include as much detail as possible:
- A clear description of the bug.
- Steps to reproduce the behavior.
- Expected vs. actual behavior.
- Details about your environment (OS, Python version).

### Suggesting Enhancements

If you have an idea for a new feature or an improvement, we'd love to hear it! Please use the **Feature Request** template when opening an issue. Explain *why* this feature would be useful and how it aligns with the project's goals.

### Pull Requests

1. **Fork** the repository and clone it locally.
2. **Create a branch** for your feature or bug fix (`git checkout -b feature/my-awesome-feature` or `git checkout -b fix/issue-number`).
3. **Make your changes**. Keep them focused and concise.
4. **Test** your changes to ensure they don't break existing functionality.
5. **Commit** your changes with a descriptive commit message (`git commit -m "Add cool feature X"`).
6. **Push** to your fork (`git push origin feature/my-awesome-feature`).
7. **Open a Pull Request** against the `main` branch. Fill out the Pull Request template provided.

## Local Development Setup

The project is designed to be lightweight and easy to run locally.

1. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/ai-audit-shelf.git
   cd ai-audit-shelf
   ```

2. (Optional but recommended) Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. Install dependencies for the API server:
   ```bash
   pip install fastapi uvicorn requests
   ```

4. Run the API locally:
   ```bash
   python api.py
   ```

5. Open the Dashboard:
   Open `dashboard.html` in your web browser.

## Styleguides

- **Python Code**: We aim to follow standard PEP 8 guidelines. Keep the code simple, readable, and standard-library focused where possible.
- **Frontend Code**: Keep the HTML/CSS/JS in `dashboard.html` clean. Avoid adding heavy external frontend dependencies unless discussed first.

Thank you for contributing to AI Audit Shelf!