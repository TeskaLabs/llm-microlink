import os
import shutil
import yaml

MY_DIR = os.path.dirname(os.path.abspath(__file__))

async def init_parser_builder(app, conversation):

	input_params_schema = "ECS"
	input_params_logs = "unify"

	await app.SandboxService.init_sandbox(conversation)

	os.makedirs(os.path.join(conversation.sandbox.path, "log"), exist_ok=True)


	# Load the schema

	with open(os.path.join(MY_DIR, "schema", "{}.yaml".format(input_params_schema)), "r") as f:
		schema_obj = yaml.safe_load(f)

	# Remove fields from the schema that are not relevant to the parser builder
	def field_filter(k):
		if k.startswith('lmio.'):
			return True
		return False
	schema_obj['fields'] = {
		k: v for k, v in schema_obj['fields'].items() if not field_filter(k)
	}

	schema = "### Schema in YAML\n\n```\n"
	schema += yaml.dump(schema_obj, indent=2)
	schema += "\n```\n"
	conversation.instructions.append(schema)

	# Also copy the schema to the sandbox
	shutil.copy(
		os.path.join(MY_DIR, "schema", "{}.yaml".format(input_params_schema)),
		os.path.join(conversation.sandbox.path, "{}.yaml".format(input_params_schema))
	)


	# Load the sample logs

	sample_logs = "## Sample Logs\n"

	srcdir = os.path.join(MY_DIR, "log", input_params_logs)
	for file in os.listdir(srcdir):
		if file.endswith(".log"):
			shutil.copy(
				os.path.join(srcdir, file),
				os.path.join(conversation.sandbox.path, "log")
			)

			sample_logs += f"log/{file}:\n"
			sample_logs += open(os.path.join(srcdir, file), "r").read()
			sample_logs += "\n\n"

	conversation.instructions.append(sample_logs)
