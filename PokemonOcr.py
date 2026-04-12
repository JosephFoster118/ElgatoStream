"""Thread-safe OCR reader with Pokémon name fuzzy matching."""

import threading
import numpy as np
import easyocr
from rapidfuzz import process, fuzz
import json


def PreprocessImage(image: np.ndarray, threshhold: int) -> np.ndarray:
    """Simple preprocessing: set pixels below the threshold to black, the remaining to full white."""
    if image.ndim == 3:
        # Equivalent to "all channels >= threshold" but typically faster and with fewer temporaries.
        mask = np.min(image, axis=-1) >= threshhold
    else:
        mask = image >= threshhold

    image[...] = 0
    image[mask] = 255
    return image

class ImageSectionParameters:
    """Defines the top-left and bottom-right coordinates of a rectangular image section."""
    def __init__(self, top_left: tuple[int, int], bottom_right: tuple[int, int]):
        self.top_left = top_left
        self.bottom_right = bottom_right

    def __repr__(self) -> str:
        return f"ImageSectionParameters(top_left={self.top_left}, bottom_right={self.bottom_right})"

class PokemonOcr:
    """Simple interface: feed in a cropped BGR/RGB numpy image, get a Pokémon name back.

    Usage:
        ocr = PokemonOcr(pokemon_names, gpu=True)
        name = ocr.read(cropped_image)          # returns best-match Pokémon name or None
        name, score = ocr.readWithScore(img)    # also returns the fuzzy match score
    """

    def __init__(self, pokemon_names: list[str], *, gpu: bool = True,
                 score_threshold: int = 60):
        """
        Args:
            pokemon_names: Full list of valid Pokémon names.
            gpu:           Use CUDA for EasyOCR (falls back to CPU if unavailable).
            score_threshold: Minimum rapidfuzz score (0-100) to accept a match.
        """
        self._lock = threading.Lock()
        self._reader = easyocr.Reader(["en"], gpu=gpu)
        self._names = list(pokemon_names)
        self._threshold = score_threshold
        self.image_section_parameters: dict[str, dict[str, ImageSectionParameters]] = {}

    def read(self, image: np.ndarray) -> str | None:
        """Return the best-matching Pokémon name, or None if nothing matched."""
        name, _ = self.readWithScore(image)
        return name

    def readWithScore(self, image: np.ndarray) -> tuple[str | None, float]:
        """Return (matched_name, score) or (None, 0.0)."""
        raw = self._ocr(image)
        if not raw:
            return None, 0.0
        return self._match(raw)

    def _ocr(self, image: np.ndarray) -> str:
        """Run EasyOCR on the image. Thread-safe."""
        with self._lock:
            results = self._reader.readtext(image, detail=0)
        return " ".join(results).strip()

    def _match(self, raw_text: str) -> tuple[str | None, float]:
        """Fuzzy-match raw OCR text against the Pokémon name list."""
        result = process.extractOne(
            raw_text, self._names, scorer=fuzz.WRatio
        )
        if result is None:
            return None, 0.0
        name, score, _ = result
        if score >= self._threshold:
            return name, score
        return None, score

    def addImageSectionParameters(self, name: str, parameters: dict[str, ImageSectionParameters]) -> None:
        """Add or replace one named image section group (for example: 'singles')."""
        self.image_section_parameters[name] = dict(parameters)

    def addImageSectionParametersFromJson(self, name: str, json_path: str) -> None:
        """Load one named image section group from JSON.

        Expected JSON format:
        {
            "opponent": {"top_left": [x, y], "bottom_right": [x, y]},
            "player": {"top_left": [x, y], "bottom_right": [x, y]}
        }
        Stored as:
            image_section_parameters[name]["opponent"]
            image_section_parameters[name]["player"]
        """
        with open(json_path, "r") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Expected top-level JSON object in {json_path}")

        loaded: dict[str, ImageSectionParameters] = {}
        for section_name, section_data in data.items():
            if not isinstance(section_data, dict):
                continue
            if "top_left" not in section_data or "bottom_right" not in section_data:
                continue

            loaded[section_name] = ImageSectionParameters(
                top_left=tuple(section_data["top_left"]),
                bottom_right=tuple(section_data["bottom_right"]),
            )

        if not loaded:
            raise ValueError(
                f"No valid section entries found in {json_path}. "
                "Expected top_left/bottom_right coordinates."
            )

        self.image_section_parameters[name] = loaded

    def processImageSections(self, image: np.ndarray, section_group: str) -> dict[str, np.ndarray]:
        """Crop the specified sections from the image and return them as a dict.

        For example, if section_group is "singles", it will look for:
            image_section_parameters["singles"]["opponent"]
            image_section_parameters["singles"]["player"]

        Returns a dict like:
            {"opponent": opponent_image, "player": player_image}
        """
        if section_group not in self.image_section_parameters:
            raise ValueError(f"Section group '{section_group}' not found.")

        sections = self.image_section_parameters[section_group]
        cropped_images = {}
        for name, params in sections.items():
            x1, y1 = params.top_left
            x2, y2 = params.bottom_right
            cropped_images[name] = image[y1:y2, x1:x2]

        #preprocess the cropped images
        for name, img in cropped_images.items():
            cropped_images[name] = PreprocessImage(img, 180)

        return cropped_images

    def ocrSections(self, image: np.ndarray, section_group: str) -> dict[str, tuple[str | None, float]]:
        """Run OCR and matching on each section in the specified group.

        Returns a dict like:
            {"opponent": (name, score), "player": (name, score)}
        """
        sections = self.processImageSections(image, section_group)
        results = {}
        for name, img in sections.items():
            results[name] = self.readWithScore(img)
        return results
    

#Main function for testing
if __name__ == "__main__":
    import glob
    from PIL import Image

    pokemon_names_path = "resources/pokemon_names.json"
    with open(pokemon_names_path, "r") as f:
        pokemon_names = json.load(f)

    pokemon_ocr = PokemonOcr(pokemon_names, gpu=True)
    pokemon_ocr.addImageSectionParametersFromJson("singles", "resources/singles_pokemon_locations.json")

    screenshot_paths = sorted(glob.glob("screenshots/*.png"))
    if not screenshot_paths:
        print("No screenshots found in screenshots/")
    else:
        for file_path in screenshot_paths:
            print(f"\n{file_path}")
            img = np.array(Image.open(file_path))
            results = pokemon_ocr.ocrSections(img, "singles")
            for section, (name, score) in results.items():
                print(f"  {section}: {name} (score: {score:.2f})")
    

