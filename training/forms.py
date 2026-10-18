from typing import cast

from django import forms

from .models import Person, SquadAssignment


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = SquadAssignment
        fields = ["person", "role", "valid_from"]
        widgets = {"valid_from": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, squad, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.squad = squad
        person_field = cast(forms.ModelChoiceField, self.fields["person"])
        person_field.queryset = Person.objects.filter(club=squad.club, is_active=True)
