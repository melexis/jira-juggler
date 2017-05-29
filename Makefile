
RM = rm -rf
PYTHON = python3
PYLINT = pylint3
SCRIPT = jira_juggler.py
QUERY = "project = MLX90373 and sprint = 90373_ABB and component = \"[SW]\" "
PREAMBLE_FILE = preamble.tjp
TASK_FILE = jira_export.tjp
POSTAMBLE_FILE = postamble.tjp
FULL_FILE = full_file.tjp
TASK_JUGGLER = tj3

.PHONY: all
all: clean $(FULL_FILE)
	$(TASK_JUGGLER) $(FULL_FILE)

$(FULL_FILE): $(PREAMBLE_FILE) $(TASK_FILE) $(POSTABMLE_FILE)
	cat $(PREAMBLE_FILE) > $(FULL_FILE)
	cat $(TASK_FILE) >> $(FULL_FILE)
	cat $(POSTAMBLE_FILE) >> $(FULL_FILE)

$(TASK_FILE): $(SCRIPT)
	$(PYTHON) $(SCRIPT) -o $(TASK_FILE) -q $(QUERY) -u $$USER -l warning

.PHONY: clean
clean:
	$(RM) $(TASK_FILE) $(FULL_FILE)

.PHONY: lint
lint:
	$(PYLINT) --rcfile=../pylint.rc $(SCRIPT)
