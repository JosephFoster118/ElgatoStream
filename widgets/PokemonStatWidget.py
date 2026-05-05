from PySide6.QtCore import Qt, QTimer
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
        self.pokemon_name = ""
        self.stats = None
        self.mega_stats = None
        self._showing_mega = False
        self._alternate_period_ms = 1000
        self._alternate_timer = QTimer(self)
        self._alternate_timer.setInterval(self._alternate_period_ms)
        self._alternate_timer.timeout.connect(self._onAlternateTick)

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
        self._alternate_timer.stop()
        self._showing_mega = False
        self.pokemon_name = "Unknown"
        self.pokemon_name_label.setValue("Unknown")
        self.hp_label.setValue("--")
        self.attack_label.setValue("--")
        self.defense_label.setValue("--")
        self.sp_attack_label.setValue("--")
        self.sp_defense_label.setValue("--")
        self.speed_label.setValue("--")

    def setAlternatePeriodMs(self, period_ms: int):
        self._alternate_period_ms = max(100, int(period_ms))
        self._alternate_timer.setInterval(self._alternate_period_ms)

    def getAlternatePeriodMs(self) -> int:
        return self._alternate_period_ms

    def setAlternatePeriodSeconds(self, period_seconds: float):
        self.setAlternatePeriodMs(int(float(period_seconds) * 1000))

    def getAlternatePeriodSeconds(self) -> float:
        return self._alternate_period_ms / 1000.0

    def _renderStats(self, stats, is_mega=False):
        if isinstance(stats, dict):
            name = stats.get("name", "Unknown")
            stat_values = stats.get("stats", {})
            hp = stat_values.get("hp", "--")
            attack = stat_values.get("attack", "--")
            defense = stat_values.get("defense", "--")
            sp_attack = stat_values.get("special-attack", "--")
            sp_defense = stat_values.get("special-defense", "--")
            speed = stat_values.get("speed", "--")
        else:
            name = getattr(stats, "name", "Unknown")
            hp = getattr(stats, "hp", "--")
            attack = getattr(stats, "attack", "--")
            defense = getattr(stats, "defense", "--")
            sp_attack = getattr(stats, "special_attack", "--")
            sp_defense = getattr(stats, "special_defense", "--")
            speed = getattr(stats, "speed", "--")

        self.pokemon_name = str(name)
        display_name = self.pokemon_name
        if is_mega and "mega" not in display_name.lower():
            display_name = f"{display_name} (Mega)"

        self.pokemon_name_label.setValue(display_name)
        self.hp_label.setValue(hp)
        self.attack_label.setValue(attack)
        self.defense_label.setValue(defense)
        self.sp_attack_label.setValue(sp_attack)
        self.sp_defense_label.setValue(sp_defense)
        self.speed_label.setValue(speed)

    def _onAlternateTick(self):
        if self.stats is None or self.mega_stats is None:
            self._alternate_timer.stop()
            return

        self._showing_mega = not self._showing_mega
        if self._showing_mega:
            self._renderStats(self.mega_stats, is_mega=True)
        else:
            self._renderStats(self.stats, is_mega=False)

    def _extractName(self, stats):
        if stats is None:
            return None
        if isinstance(stats, dict):
            return stats.get("name", None)
        return getattr(stats, "name", None)

    def updateStats(self, stats, mega_stats=None):
        if stats is None:
            self._setUnknown()
            return

        previous_name = self._extractName(self.stats)
        incoming_name = self._extractName(stats)
        same_pokemon = previous_name is not None and incoming_name == previous_name
        had_mega = self.mega_stats is not None
        has_mega = mega_stats is not None
        mega_mode_changed = had_mega != has_mega

        self.stats = stats
        self.mega_stats = mega_stats

        if same_pokemon and not mega_mode_changed:
            if self._showing_mega and has_mega:
                self._renderStats(self.mega_stats, is_mega=True)
            else:
                self._renderStats(self.stats, is_mega=False)
        else:
            self._showing_mega = False
            self._renderStats(self.stats, is_mega=False)

        if has_mega:
            if not self._alternate_timer.isActive():
                self._alternate_timer.start()
        else:
            self._alternate_timer.stop()
