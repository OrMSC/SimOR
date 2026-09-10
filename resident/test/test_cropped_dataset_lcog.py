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
        "-c", os.path.join(resident_dir, "configs_lcog"),
        "-c", os.path.join(resident_dir, "configs"),
        "-d", os.path.join(resident_dir, "model_data/lcog/data_cropped"),
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


if __name__ == "__main__":
    test_cropped_example()
    print("Test passed: Model ran to completion.")