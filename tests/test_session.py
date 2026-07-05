from brain.session.session import Session
from brain.session.context_builder import ContextBuilder


def divider(title: str):

    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


session = Session()

builder = ContextBuilder()

# ----------------------------------------------------------
divider("Conversation")

session.add_user("Who's Elon Musk?")

session.add_assistant("Elon Musk is the CEO of Tesla.")

print(session.conversation.transcript())

# ----------------------------------------------------------
divider("Entity Memory")

session.entities.remember(
    "person",
    "Elon Musk",
)

print(session.entities.all)

# ----------------------------------------------------------
divider("Topic")

session.topic.update(
    "Elon Musk"
)

print(session.topic.current)

# ----------------------------------------------------------
divider("Reference Resolution")

context = builder.build(

    session=session,

    message="Where was he born?",

)

print(context)

# ----------------------------------------------------------
divider("Another Turn")

session.add_user(
    "Where was he born?"
)

session.add_assistant(
    "He was born in Pretoria."
)

print(session.conversation.transcript())

# ----------------------------------------------------------
divider("Project Memory")

session.entities.remember(
    "project",
    "Mike",
)

session.entities.remember(
    "language",
    "Python",
)

print(session.entities.all)

# ----------------------------------------------------------
divider("Context")

print(

    builder.build(

        session=session,

        message="Tell me more about him.",

    )

)