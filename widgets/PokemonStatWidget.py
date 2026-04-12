from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QWidget

from .DraggableWidget import DraggableWidget


#A widget with 2 labels, one for the name and one for the stats. The stats label is updated with the stats of the pokemon.
#Uses a horizontal layout to display the name and stats side by side.
#Stat name is left aligned and stat value is right aligned. The name label is above the stats label.
#It will resize to fit the content, but has a minimum size to prevent it from being too small
#There is no background color, text is white
class SingleStatWidget(QWidget):
    def __init__(self, state_name: str, start_value = "-----", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        #No boarder or background, just text
        self.setStyleSheet(
            "background-color: rgba(0, 0, 0, 0);"
            "color: white;"
            "border: none;"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        self.name_label = QLabel(state_name + ": ")
        self.stat_label = QLabel(str(start_value))
        self.stat_label.setAlignment(Qt.AlignRight)
        layout.addWidget(self.name_label)
        layout.addWidget(self.stat_label)

    def setValue(self, value):
        self.stat_label.setText(str(value))

        

class PokemonStatWidget(DraggableWidget):
    def __init__(self, widget_header, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.setStyleSheet(
            "background-color: rgba(0, 0, 0, 160);"
            "color: white;"
            "border: 1px solid #666;"
            "border-radius: 6px;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        self.header_label = QLabel(widget_header)
        self.header_label.setAlignment(Qt.AlignCenter)
        self.header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.header_label)

        self.pokemon_name_label = SingleStatWidget("Name")
        self.hp_label = SingleStatWidget("HP")
        self.attack_label = SingleStatWidget("Attack")
        self.defense_label = SingleStatWidget("Defense")
        self.sp_attack_label = SingleStatWidget("Sp. Atk")
        self.sp_defense_label = SingleStatWidget("Sp. Def")
        self.speed_label = SingleStatWidget("Speed")
        layout.addWidget(self.pokemon_name_label)
        layout.addWidget(self.hp_label)
        layout.addWidget(self.attack_label)
        layout.addWidget(self.defense_label)
        layout.addWidget(self.sp_attack_label)
        layout.addWidget(self.sp_defense_label)
        layout.addWidget(self.speed_label)


    def _setUnknown(self):
        self.pokemon_name_label.setValue("Unknown")
        self.hp_label.setValue("--")
        self.attack_label.setValue("--")
        self.defense_label.setValue("--")
        self.sp_attack_label.setValue("--")
        self.sp_defense_label.setValue("--")
        self.speed_label.setValue("--")

    def updateStats(self, stats):
        if stats is None:
            self._setUnknown()
            return

        if isinstance(stats, dict):
            self.pokemon_name_label.setValue(stats.get("name", "Unknown"))
            stat_values = stats.get("stats", {})
            self.hp_label.setValue(stat_values.get("hp", "--"))
            self.attack_label.setValue(stat_values.get("attack", "--"))
            self.defense_label.setValue(stat_values.get("defense", "--"))
            self.sp_attack_label.setValue(stat_values.get("special-attack", "--"))
            self.sp_defense_label.setValue(stat_values.get("special-defense", "--"))
            self.speed_label.setValue(stat_values.get("speed", "--"))
            return

        # PokemonStats.PokemonStat object
        self.pokemon_name_label.setValue(getattr(stats, "name", "Unknown"))
        self.hp_label.setValue(getattr(stats, "hp", "--"))
        self.attack_label.setValue(getattr(stats, "attack", "--"))
        self.defense_label.setValue(getattr(stats, "defense", "--"))
        self.sp_attack_label.setValue(getattr(stats, "special_attack", "--"))
        self.sp_defense_label.setValue(getattr(stats, "special_defense", "--"))
        self.speed_label.setValue(getattr(stats, "speed", "--"))
