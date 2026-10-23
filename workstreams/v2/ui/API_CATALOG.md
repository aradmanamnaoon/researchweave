# UI API catalog

Factory: researchweave.ui.build_ui_facade(path). Exposes capability_manifest(), health(), preview(operation, arguments, context), execute(operation, arguments, context).

Operations: ui.project.list/create/open/update; ui.source.add/search/get; ui.review.vote/counts; ui.qual.annotate/list; ui.dataset.import/list/describe; ui.manuscript.save; ui.notebook.save; ui.tutorial.step; ui.activity.list; ui.preferences.read/update; ui.export.preview/write; ui.agent.propose/deny.

Additional milestone-2 operations: ui.review.queue with decision filtering and offset/limit; ui.dataset.page (bounded up to 1,000 rows) and ui.dataset.variables with inferred type and missingness warnings. Current total: 27.

For example: facade.execute('ui.project.create', {'title': 'Pilot', 'question': 'Why?', 'study_type': 'literature'}).

The preview path cannot write. Export writes require an injected trusted export_authorizer. An AI proposal cannot create authorization.
