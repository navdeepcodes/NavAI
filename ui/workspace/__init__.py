"""Mike's desktop workspace — the full application, and the corner presence.

Two states of one product:

  FULL MIKE   a real desktop window: a sidebar of surfaces (chat, history,
              memory, profile, voice, model, privacy, about) and a premium
              conversation workspace.
  CORNER MIKE a small companion that lives in the corner when the window is
              away, still listening, surfacing only what's relevant.

The engine underneath — brain, tools, voice, safety — is untouched: the
workspace implements exactly the contract UIController already speaks
(input / conversation / confirm / activity, add_user_message,
begin_mike_stream, add_action_card, set_state, and the state / dismiss /
minimise / maximise signals), so the redesign lives entirely in presentation.
"""
