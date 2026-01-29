"""
Score processing utilities for Fux Gradus ad Parnassum exercises.

This module parses MusicXML files containing musical exercises, extracts metadata,
and generates individual score segments and searchable HTML tables.

The original on-score annotations are from c.2019.
I honestly can't remember if that initial annotation
was manual, automatic, or some combination.

In any case, a spot check suggests that the data is accurate,
and we can add routines to check for sure as needed.

By:
Mark Gotham

Licence:
- Code = MIT licence, 2026
- Rendered scores = CC0 (Public Domain). Mark Gotham and FourScoreAndMore.org waive all rights to those documents.
"""

from music21 import converter, stream, metadata, expressions
import pandas as pd
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
REPO = Path(__file__).parent.resolve()

# Data extraction configuration
SEARCH_HEADERS = ["Fig. ", "Species: ", "Modal final: ", "Cantus firmus: "]
WRITE_HEADERS = ["Figure", "Species", "Modal final", "Cantus firmus"]
COLUMN_NAMES = ["Measure start"] + WRITE_HEADERS

# Metadata configuration
SCORE_TITLE = "Gradus ad Parnassum Exercise"
SCORE_COMPOSER = "Fux, Johann Joseph"

# URL configuration for downloads and viewing.
BASE_RAW_GIT = "https://raw.githubusercontent.com/MarkGotham/species/refs/heads/main/scores/1x1/"
BASE_VHV_URL = "https://verovio.humdrum.org/?file=" + BASE_RAW_GIT

# HTML template
HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>"Gradus" Scores. Search and Sort.</title>
    <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.13.4/css/jquery.dataTables.css">
    <style>
        /* Table width to prevent horizontal scroll */
        .container {{ max-width: 100%; }}
        .table {{ width: 100%; }}
    </style>
</head>
<body>
    <div class="container">
        {table_html}
    </div>

<script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
<script src="https://cdn.datatables.net/1.13.4/js/jquery.dataTables.js"></script>
<script>
    $(document).ready(function() {{
        $('#dataframe').DataTable({{
            paging: false,
            searching: true,
            ordering: true,
            search: {{
                name: 'search_input'
            }}
        }});
    }});
</script>
</body>
</html>
"""


def process_all(input_path: Path = REPO) -> None:
    """
    Process all section files in the repository.

    :param input_path: Top level of the repo.
    :return: None (writes files to disk)
    """
    for part in ["I", "II", "III"]:
        section_file = input_path / part / f"{part}-Solutions.mxl"
        try:
            process_section_file(section_file)
            logger.info(f"Successfully processed {section_file}")
        except Exception as e:
            logger.error(f"Failed to process {section_file}: {e}")


def process_section_file(
        input_path: Path,
        output_dir: Path = None,
        write_data: bool = True,
        html_table: bool = True,
        create_segments: bool = True
) -> None:
    """
    Process a whole-section score file and write data and scores depending on the arguments.

    :param input_path: Path to input file (e.g., Part 1)
    :param output_dir: Directory to save output files. Defaults to creating alongside the input.
    :param write_data: If True, write a summative tsv file with the data (for researchers).
    :param html_table: If True, write a searchable and sortable html doc (public-facing).
    :param create_segments: If True, break up a score into each figure and write to a dedicated file.
    :return: None (writes files to disk)
    """
    if not input_path.is_relative_to(REPO):
        raise ValueError(f"Input path {input_path} must be relative to repository {REPO}")

    score = converter.parse(input_path)

    # Extract data from score annotations
    data = extract_figure_data(score)

    # Create DataFrame with measure range information
    dataframe = create_dataframe_with_ranges(data, score)

    if output_dir is None:
        output_dir = input_path.parent

    if write_data:
        write_tsv(dataframe, output_dir)

    if html_table:
        write_html_table(dataframe, output_dir)

    if create_segments:
        write_score_segments(score, dataframe)


def extract_figure_data(score: stream.Score) -> list:
    """
    Extract figure metadata from text expressions in the score.

    :param score: music21 Score object
    :return: List of data rows, each containing the same data (measure_number, figure number ...)
    """
    text_expressions = score.recurse().getElementsByClass(expressions.TextExpression)
    data = []

    for text_expr in text_expressions:
        measure_number = text_expr.getContextByClass(stream.Measure).number
        text_components = text_expr.content.split("; ")

        if len(text_components) != len(SEARCH_HEADERS):
            raise ValueError(
                f"Expected {len(SEARCH_HEADERS)} components in text expression at measure {measure_number}, "
                f"got {len(text_components)}. "
                f"Raw content: {text_expr.content}"
            )

        entry = [measure_number]

        for index, header in enumerate(SEARCH_HEADERS):
            if not text_components[index].startswith(header):
                raise ValueError(
                    f"At measure {measure_number}, "
                    f"expected component at index {index} to start with '{header}', "
                    f"got '{text_components[index]}'."
                )
            entry.append(text_components[index][len(header):])

        data.append(entry)

    return data


def create_dataframe_with_ranges(data: list, score) -> pd.DataFrame:
    """
    Create a DataFrame with measure start/end ranges and counts.

    :param data: Extracted figure data
    :param score: music21 Score object for measure validation
    :return: DataFrame with columns including Measure start, Measure end, and Measure Count
    """
    dataframe = pd.DataFrame(data, columns=COLUMN_NAMES)

    # Calculate measure end positions (one before the next figure starts)
    dataframe["Measure end"] = dataframe["Measure start"].shift(-1).fillna(0).astype('int64')
    dataframe["Measure end"] = dataframe["Measure end"] - 1

    # Set the final measure end to the last measure in the score
    measure_numbers = [m.measureNumber for m in score.parts[0].getElementsByClass(stream.Measure)]

    # Validate that measure numbering is sequential
    expected_measures = list(range(1, len(measure_numbers) + 1))
    if measure_numbers != expected_measures:
        raise ValueError(
            f"Measure numbering is not a standard sequential sequence. "
            f"Expected {expected_measures}, got {measure_numbers}"
        )

    dataframe.loc[dataframe.index[-1], "Measure end"] = measure_numbers[-1]

    # Calculate measure count for each figure
    dataframe["Measure Count"] = (dataframe["Measure end"] - dataframe["Measure start"] + 1).astype('int64')

    return dataframe


def write_tsv(dataframe: pd.DataFrame, output_dir: Path) -> None:
    """
    Write DataFrame to TSV file.

    :param dataframe: Data to write
    :param output_dir: Directory to write to
    """
    output_path = output_dir / "data.tsv"
    dataframe.to_csv(output_path, sep='\t', index=False)
    logger.info(f"Wrote data to {output_path}")


def write_html_table(
        dataframe: pd.DataFrame,
        output_dir: Path
) -> None:
    """
    Generate HTML with DataTables integration for searchable/sortable display.

    :param dataframe: Data to display
    :param output_dir: Directory to write HTML file
    """
    output_path = output_dir / "search.html"

    dataframe["Direct download"] = dataframe["Figure"].apply(format_download_links)
    dataframe["View on VHV"] = dataframe["Figure"].apply(format_vhv_link)

    # Generate table HTML and add required ID
    table_html = dataframe.to_html(index=False, classes='table table-striped table-hover', border=0, escape=False)
    table_html = table_html.replace('<table', '<table id="dataframe"', 1)

    # Insert table into template
    html_content = HTML_TEMPLATE.format(table_html=table_html)

    with open(output_path, 'w') as f:
        f.write(html_content)

    logger.info(f"Wrote HTML to {output_path}")


def format_download_links(figure: str) -> str:
    """
    Create download links for MXL and KRN formats.

    :param figure: Figure name (mostly numeric, though datatype is string)
    :return: Html string for clickable links.
    """
    figure_name = figure.split(" ")[0]  # Extract just the number
    shared_url = f"{BASE_RAW_GIT}{figure_name}"
    return f'<a href="{shared_url}.mxl">.mxl</a> <a href="{shared_url}.krn">.krn</a>'


def format_vhv_link(figure: str) -> str:
    """
    Create an HTML-formatter link to Verovio Humdrum Viewer (VHV).

    :param figure: Figure name/number
    :return: URL string for clickable link to VHV.
    """
    figure_name = figure.split(" ")[0]
    return f'<a href="{BASE_VHV_URL}{figure_name}.krn">click here</a>'


def write_score_segments(
        score,
        dataframe: pd.DataFrame,
) -> None:
    """
    Create individual score files for each figure segment.

    :param score: music21 Score object
    :param dataframe: DataFrame with measure ranges
    """
    # Configure score metadata
    configure_score_metadata(score)

    # Create output directory for segments
    segment_dir = REPO / "1x1"
    segment_dir.mkdir(exist_ok=True)

    # Write each segment
    for _, row in dataframe.iterrows():
        section = score.measures(row["Measure start"], row["Measure end"])
        # Extract figure number (without any comment text)
        figure_name = row["Figure"].split(" ")[0]
        if figure_name.startswith("8"):  # Not ideal, but we follow Fux
            figure_name = "0" + figure_name
        else:
            figure_name = figure_name.zfill(3)
        output_path = segment_dir / figure_name
        section.write("mxl", output_path)

    logger.info(f"Wrote {len(dataframe)} score segments to {segment_dir}")


def configure_score_metadata(score) -> None:
    """
    Set part names and score metadata.

    :param score: music21 Score object to configure (modified in place)
    """
    # Set part names to numeric identifiers
    for i, part in enumerate(score.parts):
        part.partName = str(i + 1)
        part.partAbbreviation = ""

    # Set score metadata
    score.insert(0, metadata.Metadata())
    score.metadata.title = SCORE_TITLE
    score.metadata.movementName = SCORE_TITLE  # Duplicate for display purposes
    score.metadata.composer = SCORE_COMPOSER


if __name__ == "__main__":
    process_all()