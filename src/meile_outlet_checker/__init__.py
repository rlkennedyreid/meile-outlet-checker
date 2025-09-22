import shutil
from functools import partial
from io import StringIO
from json import load
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep
from typing import Annotated, Optional

from appdirs import user_cache_dir
from fuzzysearch import find_near_matches
from pydantic import BaseModel
from pypdf import PdfReader
from requests import get, post
from rich.console import Console
from schedule import every, run_pending
from typer import Option, Typer

from .utils import console as std_console
from .utils import create_directory, package

app = Typer()


class CodeInfo(BaseModel):
    code: str
    extra: str


class Input(BaseModel):
    codes: list[CodeInfo]


def replace_if_different(new_file: Path, old_file: Path) -> bool:
    """Replace old_file with new_file if contents differ. Return True if replaced, False otherwise."""
    if not new_file.exists():
        std_console.print(f"New file {new_file} does not exist; cannot replace.")
        return False  # New file does not exist

    if old_file.exists():
        with open(new_file, "rb") as f1, open(old_file, "rb") as f2:
            if f1.read() == f2.read():
                std_console.print("Files are identical; not replacing.")
                return False  # Files are identical

    shutil.move(new_file, old_file)
    return True


def download_pdf(url: str, filename: str, dest: Path) -> tuple[bool, Path]:
    std_console.print(f"Downloading PDF from {url}")

    response = get(url, timeout=10)
    response.raise_for_status()

    final_path = dest / filename
    with TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / filename
        with open(tmp_path, "wb") as f:
            f.write(response.content)
            std_console.print(f"Saved PDF to {tmp_path}")

        replaced = replace_if_different(new_file=tmp_path, old_file=(dest / filename))

    return replaced, final_path


def send_signal_message(
    message: str,
    number: str,
    recipients: list[str],
    url: str,
) -> dict:
    payload = {"message": message, "number": number, "recipients": recipients}
    headers = {"Content-Type": "application/json"}
    response = post(url, json=payload, headers=headers, timeout=10)
    response.raise_for_status()
    return response.json()


def parse_and_notify_pdf(
    number: Optional[str],
    recipients: Optional[list[str]],
    signal_url: str,
    url: str,
    directory: Path,
    file: str,
    input_data: Input,
):
    std_console.print(f"Using directory: {directory}")
    create_directory(directory)

    replaced = False

    old_file = directory / file

    counter = 0
    while not replaced:
        counter += 1
        if counter > 90:
            std_console.print("Failed to download new file after 60 attempts; exiting.")
            return
        std_console.print("Trying download...")
        replaced, old_file = download_pdf(
            url=url,
            filename=file,
            dest=directory,
        )
        if not replaced:
            std_console.print("No new file downloaded; will retry in 60 seconds.")
            sleep(60)
        else:
            std_console.print("New file downloaded.")

    # open the pdf file
    std_console.print(f"Parsing PDF at {old_file}")
    reader = PdfReader(old_file)

    # get number of pages
    num_pages = len(reader.pages)
    buffer = StringIO()

    console = Console(file=buffer)
    std_console.print(f"Number of pages: {num_pages}")
    # define key terms

    found_matches = False
    # for s in string or []:
    for code_info in input_data.codes:
        # extract text and do the search
        matches = []
        for page in reader.pages:
            text = page.extract_text()
            text = "".join(text.split())

            matches.extend(
                find_near_matches(
                    "".join(code_info.code.split()),
                    text,
                    max_l_dist=0,
                )
            )

        if matches:
            found_matches = True
            console.print(f"Found {len(matches)} matches for '{code_info.code}'")
            console.print(f"{code_info.extra}:")

            for match in matches:
                console.print(f"    '{match.matched}' with {match.dist} differences")

    if found_matches:
        console.print(f"{url}")
        output = buffer.getvalue().strip()
        std_console.print(output)

        if number and not recipients:
            recipients = [number]

        if number and recipients:
            send_signal_message(
                message=output,
                number=number,
                recipients=recipients,
                url=signal_url,
            )
    else:
        std_console.print("No matches found.")


def load_input_from_json(path: Path) -> Input:
    with open(path, "r", encoding="utf-8") as f:
        data = load(f)
    return Input(**data)


@app.command()
def default(
    number: Annotated[
        Optional[str],
        Option(help="Phone number to send Signal message from"),
    ] = None,
    recipients: Annotated[Optional[list[str]], Option()] = None,
    signal_url: str = "http://localhost:8080/v2/send",
    url: Annotated[
        str,
        Option(help="URL of the Meile Outlet pricelist PDF"),
    ] = "https://application.miele.co.uk/resources/pdf/MieleOutletPricelist.pdf",
    directory: Annotated[
        Path,
        Option(
            help="Directory to save the downloaded PDF",
            dir_okay=True,
            resolve_path=True,
            file_okay=False,
            show_default=False,
        ),
    ] = Path(
        user_cache_dir(appname=package()),
    ).resolve(),
    file: Annotated[
        str,
        Option(help="Filename to save the PDF as"),
    ] = "MieleOutletPricelist.pdf",
    input_file: Annotated[
        Path,
        Option(
            help="Path to input JSON file",
            dir_okay=False,
            file_okay=True,
            exists=True,
        ),
    ] = Path("input.json"),
    once: Annotated[bool, Option(help="Run once and exit")] = False,
) -> None:
    input_data = load_input_from_json(input_file)

    if once:
        parse_and_notify_pdf(
            number=number,
            recipients=recipients,
            signal_url=signal_url,
            url=url,
            directory=directory,
            file=file,
            input_data=input_data,
        )
        return

    every().day.at("09:00", tz="Europe/London").do(
        partial(
            parse_and_notify_pdf,
            number=number,
            recipients=recipients,
            signal_url=signal_url,
            url=url,
            directory=directory,
            file=file,
            input_data=input_data,
        )
    )
    while True:
        run_pending()
        sleep(1)


def main() -> None:
    app()
