import json
import subprocess
from pathlib import Path
from typing import Sequence

# Configuration
MUSESCORE_EXECUTABLE_BASE =  Path("/Users/<user>/Applications/")
MSCORE_4_EXECUTABLE = str(MUSESCORE_EXECUTABLE_BASE / "MuseScore 4.app/Contents/MacOS/mscore")
DEFAULT_INPUT_DIR = Path("../")

VALID_INPUT_EXTENSIONS = {"*.mscx", "*.mscz"}
VALID_OUTPUT_EXTENSIONS = {".mxl", ".pdf"}

def _build_jobs_for_file(
        file_path: Path,
        output_formats: Sequence[str],
        overwrite: bool = False,
) -> list[dict]:
    """
    Build the batch-job JSON entries for a single input file.

    Params:
    file_path: path to input file
    output_formats: output formats to produce, e.g. (".pdf", ".mxl").
    overwrite: If False, skip full-score outputs that already exist
        (sic, doesn't apply to parts: see note above)
    """
    jobs = []

    for output_format in output_formats:
        if not output_format.startswith("."):
            raise ValueError(f"output_format must start with '.': {output_format!r}")

        output_file = file_path.with_suffix(output_format)
        if not overwrite and output_file.exists():
            print(f"Skipping (already exists): {output_file}")
            continue
        jobs.append({
            "in": str(file_path),
            "out": str(output_file),
        })

    return jobs


def convert_directory(
        input_dir: Path = DEFAULT_INPUT_DIR,
        input_extensions: Sequence[str] = ("*.mscz",),
        output_formats: Sequence[str] = (".pdf", ".mxl"),
        musescore_executable: str = MSCORE_4_EXECUTABLE,
        overwrite: bool = False
):
    """
    Set up and implement a batch conversion.

    Params:
    input_dir: directory to search (recursively) for input files.
    input_extensions: glob patterns to search for, e.g. ("*.mscx",).
    output_formats: output extensions to produce, e.g. (".pdf", ".mxl").
    musescore_executable: path to the mscore binary to invoke.
    overwrite: if False, skip full-score outputs that already exist
        instead of regenerating them.
        No effect on parts exports (see note above).
    """
    input_dir = input_dir.resolve()

    if not input_dir.exists():
        print(f"Error: Directory '{input_dir}' does not exist.")
        return

    for ext in input_extensions:
        if ext not in VALID_INPUT_EXTENSIONS:
            raise ValueError(f"Unsupported input extension: {ext!r}")

    files = []
    for ext in input_extensions:
        files.extend(input_dir.rglob(ext))

    if not files:
        print(f"No MuseScore files found in '{input_dir}'.")
        return

    print(f"Found {len(files)} files in '{input_dir}'. Preparing batch job...")

    # Create job list for JSON
    job_data = []
    for file_path in files:
        job_data.extend(_build_jobs_for_file(file_path, output_formats, overwrite))

    if not job_data:
        print("Nothing to do - all outputs already exist (use overwrite=True to force).")
        return

    json_file = input_dir / "batch_job.json"
    try:
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(job_data, f, indent=2)

        print(f"Running conversion via '{musescore_executable}' ({len(job_data)} job(s))...")

        # Execute MuseScore with the job file
        # Using check=True raises an error if the command fails
        subprocess.run([musescore_executable, "-j", str(json_file)], check=True)

        print("Batch conversion complete.")

    except FileNotFoundError:
        print(
            f"Error: MuseScore executable '{musescore_executable}' not found. "
            "Please ensure it is installed and in your PATH."
        )
    except subprocess.CalledProcessError as e:
        print(f"Conversion failed with error code {e.returncode}. Check MuseScore output for details.")
    finally:
        # Clean up the temporary JSON file
        if json_file.exists():
            json_file.unlink()


def main():
    """All standard conversions at once"""
    convert_directory(
        input_extensions=("*.mscz",),
        output_formats=(".pdf", ".mxl",),
        overwrite=False,
        musescore_executable=MSCORE_4_EXECUTABLE
    )


if __name__ == "__main__":
    main()
