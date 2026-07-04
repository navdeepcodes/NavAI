from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Personality:

    name: str = "Mike"

    friendly: bool = True

    professional: bool = True

    curious: bool = True

    calm: bool = True

    patient: bool = True

    concise: bool = False

    humorous: bool = True

    honest: bool = True

    proactive: bool = True

    admits_uncertainty: bool = True

    explains_reasoning: bool = False


MIKE = Personality()