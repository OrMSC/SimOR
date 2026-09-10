import subprocess
import os
import sys

def test_cropped_example():
    """
    Run the cropped dataset example.
    Test passes if the model runs to completion, fails if it crashes.
    """

    # Get the path to simulation.py relative to this test file
    test_dir = os.path.dirname(__file__)
    resident_dir = os.path.dirname(test_dir)
    file_path = os.path.join(resident_dir, "simulation.py")

    run_args = [
        "-c", os.path.join(resident_dir, "configs"),
        "-d", os.path.join(resident_dir, "model_data/metro/data_cropped"),
        "-o", os.path.join(resident_dir, "outputs/test")
    ]

    # Run the simulation - subprocess.run with check=True will raise
    # CalledProcessError if the process returns a non-zero exit code
    try:
        result = subprocess.run(
            [sys.executable, file_path] + run_args,
            check=True,
            capture_output=True,
            text=True
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
    except subprocess.CalledProcessError as e:
        # Print full output on failure so CI logs show what went wrong
        print("=== STDOUT ===")
        print(e.stdout)
        print("=== STDERR ===")
        print(e.stderr, file=sys.stderr)
        raise  # Re-raise to fail the test
    
    return True


def test_cropped_visualizer():
    """
    Run the visualizer on the cropped dataset outputs.
    Test passes if the exported HTML dashboard is produced.
    """

    test_dir = os.path.dirname(__file__)
    resident_dir = os.path.dirname(test_dir)
    repo_dir = os.path.dirname(resident_dir)

    visualizer_dir = os.path.join(repo_dir, "ext_dependencies", "activitysim_visualizer")
    run_script = os.path.join(visualizer_dir, "run.py")

    # Prefer the visualizer's own virtual environment, which has its dependencies
    venv_python = os.path.join(visualizer_dir, ".venv", "Scripts", "python.exe")
    if not os.path.exists(venv_python):
        venv_python = os.path.join(visualizer_dir, ".venv", "bin", "python")
    python_exe = venv_python if os.path.exists(venv_python) else sys.executable

    output_html = os.path.join(repo_dir, "metro_cropped.html")
    if os.path.exists(output_html):
        os.remove(output_html)

    run_args = [
        "--config", "resident/configs_visualizer/metro_cropped.yaml",
        "--export-html", "metro_cropped.html",
    ]

    print(f"Running from directory {os.getcwd()}")
    try:
        result = subprocess.run(
            [python_exe, run_script] + run_args,
            cwd=repo_dir,
            check=True,
            capture_output=True,
            text=True
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
    except subprocess.CalledProcessError as e:
        print("=== STDOUT ===")
        print(e.stdout)
        print("=== STDERR ===")
        print(e.stderr, file=sys.stderr)
        raise

    assert os.path.exists(output_html), f"Expected visualizer output not found: {output_html}"

    return True


if __name__ == "__main__":
    test_cropped_example()
    print("Test passed: Model ran to completion.")
    test_cropped_visualizer()
    print("Test passed: Visualizer HTML exported.")