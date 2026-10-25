
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)


def generate_commit_messages(diff: str) -> str:
    response = client.chat.completions.create(
        model="llama3.2:3b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You generate clear Git commit messages using "
                    "Conventional Commits. Suggest exactly 3 different "
                    "commit messages based only on the provided code "
                    "changes. Keep each message short. Do not invent "
                    "changes. Number the suggestions from 1 to 3."
                )
            },
            {
                "role": "user",
                "content": f"Generate commit messages for these Git changes:\n\n{diff}"
            }
        ],
        temperature=0.3
    )

    return response.choices[0].message.content or ""
