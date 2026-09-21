"""Run with: uv run python examples/research.py --model PROVIDER:MODEL 'question'"""

import argparse

from dotenv import load_dotenv

from paper_research import create_research_agent


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Research papers with local tools")
    parser.add_argument("question")
    parser.add_argument("--model", required=True, help="Provider:model identifier")
    parser.add_argument("--workspace", default="research_data")
    args = parser.parse_args()
    agent = create_research_agent(args.model, args.workspace)
    result = agent.invoke({"messages": [{"role": "user", "content": args.question}]})
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
