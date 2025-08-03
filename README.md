# Extractly
A sundai hack

This is an AWS Lambda Function that creates a Webhook endpoint. When emails are forwarded to that webhook, the code will check if any tasks are described in the email (using openai gpt-4o as a task extractor), and add the tasks to the corresponding users todoist app.
