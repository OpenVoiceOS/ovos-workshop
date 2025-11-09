from ovos_workshop.skills.converse import ConversationalSkill


class ActiveSkill(ConversationalSkill):
    def bind(self, bus):
        super(ActiveSkill, self).bind(bus)
        if bus:
            """ insert skill in active skill list on load """
            self.activate()

    def handle_skill_deactivated(self, message=None):
        """
        skill is always in active skill list, ie, converse is always called
        """
        self.activate()


