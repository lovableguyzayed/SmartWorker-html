"""Scripts that are run by hand, not imported by the running app.

There is one exception and it is deliberate: routes.one_time_setup imports
seed_uttaranchal, because the owner of a hosted deployment has no shell to
run it from. That import is inside the view function rather than at module
level, so a function that can empty the database is only loaded when
somebody has deliberately asked for it.
"""
