import os
import re
import sys
import json
import requests
import argparse
import anthropic

from bs4 import BeautifulSoup
from dotenv import load_dotenv


def is_valid_file(file):
    return os.path.isfile(os.path.abspath(file))


def read_file_contents(file):
    file_path = os.path.abspath(file)
    try:
        with open(file_path, "r") as file:
            return file.read().strip()
    except FileNotFoundError:
        raise FileNotFoundError(f"Input file not found: {file_path}")


def download_webpage_recursive(url, depth=1):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text()

    if 1 < depth:
        base_url = url.split("//")[-1].split("/")[0]

        for link in soup.find_all("a"):
            href = link.get("href")

            if href:
                if href.startswith(("http://", "https://")) and base_url in href:
                    text += "\n\n" + download_webpage_recursive(href, depth - 1)
                elif href != "/" and not href.startswith(("http://", "https://")):
                    text += "\n\n" + download_webpage_recursive(
                        "http://" + base_url + href, depth - 1
                    )
    return text


def main(args):
    # Prep environment

    load_dotenv()

    # Prepare system prompt text

    system_prompt = None

    if is_valid_file(args.system):
        system_prompt = read_file_contents(args.system)
        print(f"\nSystem prompt {args.system} is being used!\n")

    # Prompt construction

    if not is_valid_file(args.input):
        print(f"\nfile {args.input} does not exist, exiting!")
        sys.exit(0)

    raw_input = read_file_contents(args.input)

    input_parts = re.split(r"(\s+)", raw_input)

    extracted_inputs = []

    for part in input_parts:
        if part.startswith(("http://", "https://")):
            extracted_inputs.append(
                "\n\n" + download_webpage_recursive(part.strip(), args.ddepth) + "\n\n"
            )
        elif is_valid_file(part):
            extracted_inputs.append("\n\n" + read_file_contents(part.strip()) + "\n\n")
        else:
            extracted_inputs.append(part)

    final_prompt = "".join(extracted_inputs)

    # First record what was prompted

    prompt_file_path = f"{os.path.splitext(args.input)[0]}_prompt.txt"

    with open(prompt_file_path, "w", encoding='utf-8') as file:
        file.write(final_prompt)

    print(f"\nFinal prompt written to {prompt_file_path}")

    # Then request inference from Anthropic's servers

    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

    if not anthropic_api_key:
        print("\nAn Anthropic API key must be specified in .dotenv, exiting!")
        sys.exit(0)

    client = anthropic.Client(api_key=anthropic_api_key)

    claude_model = os.getenv("CLAUDE_MODEL") or args.model

    print("\nSending prompt to Anthropic servers.")

    response = client.messages.create(
        messages=[{"role": "user", "content": final_prompt}],
        temperature=args.temperature,
        system=system_prompt,
        model=claude_model,
        max_tokens=4096,
    )

    print("\nServer responded with message.")

    # Collect all answers

    response_text = " ".join(
        [content.text for content in response.content if content.type == "text"]
    )

    # Then finally record the answer

    answer_file_path = (
        os.path.abspath(args.output)
        if args.output
        else os.path.abspath(os.path.splitext(args.input)[0] + "_answer.txt")
    )

    with open(answer_file_path, "w", encoding='utf-8') as file:
        file.write(response_text)

    print(f"\nAnswer saved to {answer_file_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="A python program for local interaction with Anthropic's API. You can download websites and pass them right to one of Anthropic's models."
    )

    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help='Input file path. The input file may contain both links and filepaths, both are going to be expanded in place, meaning that any website data is going to be expanded inline with text, and any filepath is going to be expanded inline with text.',
        type=str,
    )

    parser.add_argument(
        "-o",
        "--output",
        required=False,
        help="Output file path, if nothing is specified it will default to the inputs name + a suffix.",
        type=str,
    )

    parser.add_argument(
        "-t",
        "--temperature",
        required=False,
        help="Amount of randomness injected into the response. Defaults to 1.0. Ranges from 0.0 to 1.0. Use temperature closer to 0.0 for analytical / multiple choice, and closer to 1.0 for creative and generative tasks.",
        default=0,
        type=float,
    )

    parser.add_argument(
        "--system",
        required=False,
        help="System prompt file path. It will automatically look for system.txt.",
        default="system.txt",
        type=str,
    )

    parser.add_argument(
        "--model",
        required=False,
        type=str,
        help="Specify the exact version of the model to use, otherwise the latest default Opus is used.",
        default="claude-3-opus-20240229",
    )

    parser.add_argument(
        "--ddepth",
        required=False,
        help="Website download depth when recursing child links. I would recommend not setting it above 3 initially such that you don't eat up 15$ worth of tokens immediately :].",
        default=1,
        type=int,
    )

    main(parser.parse_args())
