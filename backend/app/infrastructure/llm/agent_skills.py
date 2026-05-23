from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSkill:
    name: str
    mission: str
    rules: list[str]
    output_contract: str

    def render(self) -> str:
        rules = "\n".join(f"- {rule}" for rule in self.rules)
        return (
            f"Agent Skill: {self.name}\n"
            f"Mission: {self.mission}\n"
            f"Rules:\n{rules}\n"
            f"Output contract: {self.output_contract}"
        )
