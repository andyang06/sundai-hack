import requests
from datetime import datetime
from typing import List, Optional
import json
import os

# Define your Task dataclass if not already
from dataclasses import dataclass


@dataclass
class Task:
    task_name: str
    due_date: str
    description: str
    due_time: Optional[str] = None  # Optional time in HH:MM format


os.environ["OPENAI_API_KEY"] = ""  # TODO: Add openai api key here

todoist_api_token_map = {}  # TODO: Add email address to todoist api key map here

# Updated tool schema to support multiple tasks
tool_schema = [
    {
        "type": "function",
        "function": {
            "name": "create_tasks",
            "description": "Create multiple tasks with names, due dates, and descriptions",
            "parameters": {
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "description": "List of tasks to create",
                        "items": {
                            "type": "object",
                            "properties": {
                                "task_name": {
                                    "type": "string",
                                    "description": "The name or title of the task",
                                },
                                "due_date": {
                                    "type": "string",
                                    "format": "date",
                                    "description": "The due date for the task in YYYY-MM-DD format",
                                },
                                "due_time": {
                                    "type": "string",
                                    "description": "Optional time for the task in HH:MM format (24-hour). Only include if a specific time is mentioned.",
                                },
                                "description": {
                                    "type": "string",
                                    "description": "A detailed description of the task",
                                },
                            },
                            "required": ["task_name", "due_date", "description"],
                        },
                    },
                },
                "required": ["tasks"],
            },
        },
    }
]


class TaskApplication:
    def __init__(self):
        pass

    def add_task(self, task: Task) -> bool:
        raise NotImplementedError("Subclasses must implement this method")


class TodoistApplication(TaskApplication):
    def __init__(self, api_token):
        self.api_token = api_token
        self.todoist_url = "https://api.todoist.com/rest/v2/tasks"

    def add_task(self, task: Task) -> bool:
        # Create the task in Todoist
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        # Format due date with or without time
        if task.due_time:
            # Include time in the due string
            due_string = f"{task.due_date} at {task.due_time}"
        else:
            # Date only
            due_string = task.due_date

        payload = {
            "content": task.task_name,
            "description": task.description,
            "due_string": due_string,
        }

        res = requests.post(self.todoist_url, headers=headers, json=payload)
        return res.status_code == 200 or res.status_code == 204


def extract_task_info(subject: str, body: str, sender: str) -> List[Task]:
    current_datetime = datetime.now()
    date_only = current_datetime.strftime("%Y-%m-%d")

    system_context = (
        "You are a helpful AI assistant, skilled at extracting information from arbitrary text blogs."
        f" Today's date is {date_only}. You have access to a `create_tasks` function which can be used to create"
        "any tasks you find. Extract ALL tasks mentioned in the email, not just one. If no tasks are found,"
        "return an empty list of tasks. When extracting due dates, if a specific time for a task is mentioned (e.g., '3pm', '15:30', 'at 2:30'),"
        "include it in the due_time field in 24-hour format (HH:MM). If only a date is mentioned without a specific time,"
        "leave the due_time field empty. Note that if an email has been forward, you should not extract time/date information from the email header."
    )

    api_key = os.environ["OPENAI_API_KEY"]  # Or inject securely some other way
    url = "https://api.openai.com/v1/chat/completions"

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    prompt = f"I will paste an email after this message. If there are any todos/tasks that the asks me {sender} to do, please extract ALL the information for the tasks.\nSubject: {subject}\nBody: {body}"

    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": system_context},
            {"role": "user", "content": prompt},
        ],
        "tools": tool_schema,
        "tool_choice": "auto",
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    result = response.json()

    message = result["choices"][0]["message"]
    tool_calls = message.get("tool_calls", [])

    if not tool_calls:
        return []

    function_call = tool_calls[0]["function"]
    args = json.loads(function_call["arguments"])

    # Extract tasks from the response
    tasks_data = args.get("tasks", [])
    tasks = []
    for task_data in tasks_data:
        tasks.append(Task(**task_data))

    return tasks


def lambda_handler(event, context):
    event_data = event
    print("Event:", json.dumps(event_data, indent=2))
    body = json.loads(event_data["body"])
    sender = body["headers"]["From"]
    subject = body["headers"]["Subject"].strip()
    content = body["plain"].strip()

    print("Sender:", sender)
    print("Subject:", subject)
    print("Content:", content)

    tasks = extract_task_info(subject, content, sender)

    response_body = "No tasks found."
    if tasks:
        email_addr = body["envelope"]["from"]
        if email_addr not in todoist_api_token_map:
            return {
                "statusCode": 401,
                "body": f"Didn't find mapping for email address: {email_addr}",
            }

        # Create response body with all tasks
        task_descriptions = []
        for i, task in enumerate(tasks, 1):
            time_info = f" at {task.due_time}" if task.due_time else ""
            task_descriptions.append(
                f"Task {i}:\nTask Name: {task.task_name}\nDue Date: {task.due_date}{time_info}\nDescription: {task.description}"
            )

        response_body = f"Found {len(tasks)} task(s):\n\n" + "\n\n".join(
            task_descriptions
        )
        print("Response body:", response_body)

        # Add all tasks to Todoist
        todoist = TodoistApplication(todoist_api_token_map[email_addr])
        for task in tasks:
            todoist.add_task(task)

    return {"statusCode": 200, "body": response_body}
