"""Semillas de criterios ESO Diversificación Curricular (códigos + descriptores; sin texto).

Fuente: Orden EDU/1332/2023, Anexo III.
"""

from __future__ import annotations

# Cada entrada: (nombre_materia, curso, criterios)
# criterios: ((codigo, (descriptores...)), ...)
SEED_ESO_DC: tuple[tuple[str, int, tuple[tuple[str, tuple[str, ...]], ...]], ...] = (
    (
        "Ámbito científico-tecnológico",
        3,
        (
            ("1.1", ("CCL3", "STEM2", "CC1")),
            ("1.2", ("CCL2", "CCL3", "STEM2", "CD1", "CD2")),
            (
                "1.3",
                (
                    "CCL1", "CCL2", "CCL3", "CCL5", "STEM2", "CD1", "CD2", "CD3",
                    "CPSAA3", "CPSAA4", "CPSAA5", "CC3", "CE1", "CCEC3", "CCEC4",
                ),
            ),
            ("2.1", ("CCL1", "CCL2", "CCL3", "STEM1", "STEM2", "STEM3", "STEM4")),
            (
                "2.2",
                (
                    "CCL3", "STEM1", "STEM2", "STEM3", "STEM4", "CD1", "CD2", "CD3",
                    "CD5", "CC4", "CE3", "CCEC4",
                ),
            ),
            (
                "2.3",
                (
                    "CCL2", "CCL3", "STEM1", "STEM2", "STEM3", "STEM4", "CD1", "CD2",
                    "CD3", "CD5", "CE3",
                ),
            ),
            (
                "2.4",
                (
                    "CCL1", "CCL2", "CCL3", "STEM1", "STEM2", "STEM3", "STEM4", "CD2",
                    "CD3", "CD5", "CC3", "CC4", "CE1", "CE3", "CCEC4",
                ),
            ),
            ("3.1", ("CCL1", "CCL2", "CCL3", "STEM1", "STEM2", "CD1", "CD2", "CE1")),
            (
                "3.2",
                (
                    "CCL1", "CCL3", "STEM1", "STEM2", "STEM3", "STEM5", "CD1", "CD3",
                    "CPSAA4", "CE1", "CE3",
                ),
            ),
            (
                "3.3",
                (
                    "CCL3", "STEM1", "STEM2", "STEM3", "STEM4", "STEM5", "CD1", "CD2",
                    "CD3", "CPSAA5", "CE1", "CE3",
                ),
            ),
            ("3.4", ("STEM1", "STEM2", "STEM4", "CD2", "CD3", "CPSAA4", "CE3")),
            ("3.5", ("STEM1", "STEM2", "STEM3")),
            (
                "4.1",
                (
                    "CCL1", "CCL3", "CCL5", "STEM2", "STEM4", "CD1", "CD2", "CD3", "CD4",
                    "CD5", "CPSAA3", "CE3", "CCEC3", "CCEC4",
                ),
            ),
            ("4.2", ("CP3", "STEM3", "STEM4", "STEM5", "CD3", "CPSAA3", "CE1", "CE3")),
            (
                "5.1",
                (
                    "CCL2", "STEM2", "STEM5", "CD1", "CD2", "CC2", "CC3", "CCEC1",
                    "CCEC2",
                ),
            ),
            ("5.2", ("STEM1", "STEM2", "CE1", "CE3", "CCEC1")),
            ("5.3", ("STEM1", "STEM2", "CD5", "CE1")),
            (
                "6.1",
                (
                    "CCL3", "STEM2", "STEM5", "CD3", "CD4", "CPSAA2", "CC2", "CC4",
                    "CE1",
                ),
            ),
            ("6.2", ("STEM2", "STEM5", "CD4", "CPSAA2", "CC3", "CE1")),
            (
                "6.3",
                (
                    "CCL3", "STEM2", "STEM4", "STEM5", "CD3", "CD4", "CPSAA2", "CC2",
                    "CC3", "CC4", "CE1", "CE3",
                ),
            ),
            ("6.4", ("STEM1", "STEM2", "CD5")),
            (
                "6.5",
                (
                    "CCL2", "STEM2", "STEM4", "STEM5", "CC4", "CE1", "CCEC1", "CCEC2",
                ),
            ),
            (
                "7.1",
                (
                    "STEM5", "CPSAA1", "CPSAA2", "CPSAA4", "CPSAA5", "CE1", "CE2",
                    "CCEC3",
                ),
            ),
            (
                "7.2",
                (
                    "CCL1", "CCL5", "CP3", "STEM3", "STEM5", "CPSAA3", "CC1", "CC2",
                    "CC3", "CE1", "CE3", "CCEC1",
                ),
            ),
        ),
    ),
    (
        "Ámbito científico-tecnológico",
        4,
        (
            ("1.1", ("CCL1", "CCL2", "CCL3", "STEM2", "CC1")),
            (
                "1.2",
                (
                    "CCL1", "CCL2", "CCL3", "CCL5", "CP1", "CP3", "STEM2", "CD1", "CD2",
                    "CE1",
                ),
            ),
            (
                "1.3",
                (
                    "CCL1", "CCL2", "CCL3", "CCL5", "STEM2", "CD1", "CD2", "CD3",
                    "CPSAA3", "CPSAA4", "CPSAA5", "CC3", "CE1", "CCEC3", "CCEC4",
                ),
            ),
            ("2.1", ("CCL1", "CCL2", "CCL3", "STEM1", "STEM2", "STEM3", "STEM4")),
            (
                "2.2",
                (
                    "CCL3", "STEM1", "STEM2", "STEM3", "STEM4", "CD1", "CD2", "CD3",
                    "CD5", "CC4", "CE3", "CCEC4",
                ),
            ),
            (
                "2.3",
                (
                    "CCL2", "CCL3", "STEM1", "STEM2", "STEM3", "STEM4", "CD1", "CD2",
                    "CD3", "CD5", "CE3",
                ),
            ),
            (
                "2.4",
                (
                    "CCL1", "CCL2", "CCL3", "STEM1", "STEM2", "STEM3", "STEM4", "CD2",
                    "CD3", "CD5", "CC3", "CC4", "CE1", "CE3", "CCEC4",
                ),
            ),
            (
                "3.1",
                (
                    "CCL1", "CCL2", "CCL3", "STEM1", "STEM2", "CD1", "CD2", "CPSAA4",
                ),
            ),
            (
                "3.2",
                (
                    "CCL1", "CCL3", "STEM1", "STEM2", "STEM3", "STEM5", "CD1", "CD3",
                    "CPSAA4", "CE1", "CE3",
                ),
            ),
            (
                "3.3",
                (
                    "CCL3", "STEM1", "STEM2", "STEM3", "STEM4", "STEM5", "CD1", "CD2",
                    "CD3", "CPSAA5", "CE1", "CE3",
                ),
            ),
            (
                "3.4",
                (
                    "STEM1", "STEM2", "STEM4", "CD2", "CD3", "CPSAA4", "CPSAA5", "CE3",
                ),
            ),
            ("3.5", ("STEM1", "STEM2", "STEM3")),
            (
                "4.1",
                (
                    "CCL1", "CCL3", "CCL5", "STEM2", "STEM4", "CD1", "CD2", "CD3", "CD4",
                    "CD5", "CPSAA3", "CE3", "CCEC3", "CCEC4",
                ),
            ),
            ("4.2", ("CP3", "STEM3", "STEM4", "STEM5", "CD3", "CPSAA3", "CE1", "CE3")),
            (
                "5.1",
                (
                    "CCL2", "STEM2", "STEM5", "CD1", "CD2", "CC2", "CC3", "CCEC1",
                    "CCEC2",
                ),
            ),
            ("5.2", ("STEM1", "STEM2", "CE1", "CE3", "CCEC1")),
            ("5.3", ("STEM1", "STEM2", "CD5", "CE1")),
            (
                "6.1",
                (
                    "CCL3", "STEM2", "STEM5", "CD3", "CD4", "CPSAA2", "CC2", "CC4",
                    "CE1",
                ),
            ),
            ("6.2", ("STEM2", "STEM5", "CD4", "CPSAA2", "CC3", "CE1")),
            (
                "6.3",
                (
                    "STEM2", "STEM5", "CPSAA2", "CC3", "CC4", "CE1", "CCEC1",
                ),
            ),
            ("6.4", ("CCL3", "STEM1", "STEM2", "STEM4")),
            (
                "7.1",
                (
                    "STEM5", "CPSAA1", "CPSAA2", "CPSAA4", "CPSAA5", "CE1", "CE2",
                    "CCEC3",
                ),
            ),
            (
                "7.2",
                (
                    "CCL1", "CCL5", "CP3", "STEM3", "STEM5", "CPSAA3", "CC1", "CC2",
                    "CC3", "CE1", "CE3", "CCEC1",
                ),
            ),
        ),
    ),
    (
        "Ámbito lingüístico y social",
        3,
        (
            (
                "1.1",
                (
                    "CCL1", "CCL2", "CCL3", "STEM1", "CD1", "CD3", "CPSAA4", "CC1",
                    "CCEC1",
                ),
            ),
            (
                "1.2",
                (
                    "CCL1", "CCL2", "CCL3", "STEM1", "CD1", "CD2", "CD3", "CPSAA4",
                ),
            ),
            (
                "1.3",
                (
                    "CCL1", "CCL2", "CCL3", "CCL5", "STEM1", "CD1", "CD2", "CD3",
                    "CPSAA4",
                ),
            ),
            ("1.4", ("CCL5", "STEM1", "CD2", "CD3", "CPSAA4", "CE1", "CCEC1")),
            ("2.1", ("CCL2", "STEM2", "CC1")),
            ("2.2", ("CCL3", "CD2", "CPSAA4", "CC3", "CC4")),
            ("2.3", ("CCL2", "CCL3", "CPSAA4", "CC1", "CCEC2")),
            ("2.4", ("CCL2", "STEM2", "CD1", "CPSAA4", "CCEC2")),
            ("3.1", ("CCL3", "CD3", "CC3", "CE3")),
            ("3.2", ("CCL1", "CCL2", "CCL3", "CD2")),
            ("3.3", ("CCL3", "CD2", "CC1")),
            (
                "3.4",
                (
                    "CCL1", "CCL2", "CP3", "CC1", "CE3", "CCEC1", "CCEC3",
                ),
            ),
            (
                "3.5",
                (
                    "CCL1", "CP3", "CD2", "CE3", "CCEC1", "CCEC3", "CCEC4",
                ),
            ),
            ("4.1", ("STEM1", "CPSAA2", "CC1", "CE1")),
            ("4.2", ("CCL3", "CP2", "CD2", "CPSAA1", "CE3", "CCEC1")),
            ("5.1", ("STEM3", "CC2", "CC3", "CE1")),
            (
                "5.2",
                (
                    "CCL1", "CCL2", "CCL5", "CP3", "CD3", "CPSAA3", "CC1", "CC2",
                    "CC3",
                ),
            ),
            (
                "5.3",
                (
                    "CCL1", "CCL2", "CCL5", "CP3", "CD3", "CPSAA3", "CC1", "CC2",
                    "CC3",
                ),
            ),
            ("6.1", ("CP3", "CD2", "CC1")),
            (
                "6.2",
                (
                    "CCL1", "CCL2", "CCL5", "CP2", "CP3", "CC1", "CC3", "CCEC1",
                    "CCEC2",
                ),
            ),
            ("7.1", ("CCL5", "CPSAA3", "CC3")),
        ),
    ),
    (
        "Ámbito lingüístico y social",
        4,
        (
            (
                "1.1",
                (
                    "CCL2", "CCL3", "CP2", "STEM1", "CD1", "CC1", "CE1",
                ),
            ),
            ("1.2", ("CCL1", "CCL3", "CCL5", "CP2", "CD3", "CPSAA4")),
            (
                "2.1",
                (
                    "CCL2", "CCL3", "CCL4", "CD1", "CPSAA4", "CC4", "CE3", "CCEC2",
                ),
            ),
            ("2.2", ("CCL3", "CD2", "CE3")),
            ("2.3", ("CC1", "CC3", "CE3")),
            ("2.4", ("CCL3", "STEM2", "CD1", "CPSAA4", "CC3", "CE1", "CCEC2")),
            (
                "3.1",
                (
                    "CCL2", "CCL3", "CD3", "CC1", "CC3", "CE3", "CCEC1",
                ),
            ),
            ("3.2", ("CCL3", "CD2", "CE3", "CCEC1")),
            ("3.3", ("CP3", "STEM4", "CPSAA3", "CC2")),
            ("4.1", ("CCL3", "STEM1", "CPSAA4", "CCEC1")),
            ("4.2", ("STEM5", "CD2", "CPSAA5", "CE1", "CE3")),
            (
                "5.1",
                (
                    "CCL5", "CP3", "CD3", "CPSAA3", "CC1", "CC2", "CC3", "CE1",
                    "CE3",
                ),
            ),
            (
                "5.2",
                (
                    "CCL2", "CCL5", "CP3", "CD3", "CC1", "CC2", "CC3", "CE1", "CE3",
                ),
            ),
            (
                "5.3",
                (
                    "CCL1", "CD3", "CPSAA3", "CPSAA4", "CPSAA5", "CC1", "CE3",
                ),
            ),
            (
                "6.1",
                (
                    "CCL2", "CCL5", "CP3", "CD1", "CPSAA1", "CC1", "CC3", "CCEC1",
                    "CCEC2",
                ),
            ),
            (
                "6.2",
                (
                    "CCL5", "CP3", "CC1", "CC3", "CC4", "CCEC1", "CCEC2",
                ),
            ),
            ("7.1", ("CPSAA3", "CC1", "CC3", "CE3")),
            ("7.2", ("CCL1", "CD3", "CD4", "CPSAA5", "CE3")),
            ("7.3", ("CCL1", "CD3", "CPSAA1", "CC1", "CE3")),
        ),
    ),
    (
        "Ámbito práctico",
        3,
        (
            ("1.1", ("CCL1", "CCL3", "STEM2", "CD1", "CE1")),
            ("1.2", ("CCL2", "CCL3", "STEM2", "CPSAA4", "CE1")),
            ("1.3", ("CCL1", "STEM2", "CD4", "CE1")),
            (
                "2.1",
                (
                    "CCL1", "CCL3", "STEM1", "STEM3", "CD3", "CPSAA3", "CPSAA5", "CC1",
                    "CE1",
                ),
            ),
            ("2.2", ("CCL3", "CCL5", "STEM3", "CD3", "CPSAA3")),
            (
                "3.1",
                (
                    "STEM2", "STEM5", "CD5", "CPSAA1", "CE1", "CE3", "CCEC4",
                ),
            ),
            ("3.2", ("STEM3", "STEM5", "CPSAA2", "CE1", "CE3")),
            ("4.1", ("CCL1", "STEM4", "CC4", "CCEC3", "CCEC4")),
            ("4.2", ("CCL1", "STEM4", "CD2", "CD3", "CCEC3", "CCEC4")),
            ("4.3", ("CCL1", "CD2", "CD3", "CCEC3", "CCEC4")),
            ("4.4", ("CCL1", "CD2", "CD3", "CPSAA3", "CPSAA4")),
            (
                "5.1",
                (
                    "CCL2", "STEM1", "STEM3", "CD1", "CD2", "CPSAA4", "CE1", "CE3",
                ),
            ),
            ("5.2", ("CCL2", "STEM1", "STEM3", "CD1", "CD2", "CD5", "CE3")),
            ("5.3", ("CCL2", "CD5", "CPSAA1", "CPSAA4", "CPSAA5")),
            (
                "6.1",
                (
                    "STEM1", "CD1", "CD2", "CD4", "CPSAA2", "CPSAA5",
                ),
            ),
            (
                "6.2",
                (
                    "STEM1", "STEM4", "CD1", "CD2", "CD4", "CPSAA2", "CPSAA4",
                    "CPSAA5", "CE1",
                ),
            ),
            ("6.3", ("CD1", "CD2", "CD4", "CPSAA4")),
            ("7.1", ("STEM2", "STEM5", "CD4", "CC2", "CC4")),
            ("7.2", ("STEM2", "STEM5", "CD4", "CC3", "CC4")),
        ),
    ),
    (
        "Ámbito práctico",
        4,
        (
            (
                "1.1",
                (
                    "CCL1", "CCL3", "STEM2", "CD1", "CPSAA4", "CE1",
                ),
            ),
            ("1.2", ("CCL2", "CCL3", "STEM2", "CPSAA4", "CE1")),
            ("1.3", ("CCL1", "STEM2", "CD2", "CD4", "CE1")),
            (
                "2.1",
                (
                    "CCL1", "CCL3", "STEM1", "STEM3", "CD3", "CPSAA3", "CPSAA5", "CC1",
                    "CE1", "CE3",
                ),
            ),
            (
                "2.2",
                (
                    "CCL3", "CCL5", "STEM3", "CD3", "CPSAA3", "CE1", "CE3",
                ),
            ),
            ("2.3", ("STEM1", "STEM3", "CD2", "CPSAA4")),
            ("2.4", ("STEM1", "STEM3", "CD3")),
            (
                "3.1",
                (
                    "STEM2", "STEM3", "STEM5", "CD5", "CPSAA1", "CE1", "CE3", "CCEC3",
                    "CCEC4",
                ),
            ),
            (
                "3.2",
                (
                    "STEM3", "STEM5", "CD4", "CD5", "CE1", "CE3", "CCEC3", "CCEC4",
                ),
            ),
            (
                "4.1",
                (
                    "CCL1", "CCL5", "STEM4", "CD2", "CD3", "CC4", "CCEC3", "CCEC4",
                ),
            ),
            ("4.2", ("CCL1", "CD2", "CD3", "CCEC3", "CCEC4")),
            (
                "4.3",
                (
                    "CCL1", "CD2", "CD3", "CPSAA3", "CPSAA4", "CPSAA5",
                ),
            ),
            (
                "5.1",
                (
                    "CCL2", "CP2", "STEM1", "STEM3", "CD1", "CD2", "CD5", "CPSAA4",
                    "CE1", "CE3",
                ),
            ),
            (
                "5.2",
                (
                    "CP2", "STEM1", "STEM3", "CD1", "CD2", "CD5", "CPSAA4", "CPSAA5",
                    "CE3",
                ),
            ),
            ("5.3", ("CP2", "STEM1", "STEM3", "CD2", "CD5", "CPSAA5", "CE3")),
            (
                "5.4",
                (
                    "CCL2", "CD5", "CPSAA1", "CPSAA4", "CPSAA5", "CE1",
                ),
            ),
            ("6.1", ("STEM1", "CD4", "CD5", "CPSAA5", "CE1")),
            (
                "6.2",
                (
                    "CP2", "STEM1", "CD1", "CD2", "CD4", "CD5", "CPSAA2", "CPSAA4",
                    "CPSAA5",
                ),
            ),
            (
                "6.3",
                (
                    "CP2", "STEM1", "STEM4", "CD1", "CD2", "CD4", "CD5", "CPSAA2",
                    "CPSAA4", "CPSAA5", "CE1",
                ),
            ),
            ("6.4", ("CD1", "CD2", "CD4", "CD5", "CPSAA2", "CE1")),
            ("7.1", ("STEM2", "STEM5", "CC2", "CC3", "CC4")),
            ("7.2", ("STEM2", "STEM5", "CC2", "CC4")),
            ("7.3", ("STEM2", "STEM5", "CD4", "CC2", "CC4")),
            ("7.4", ("STEM2", "STEM5", "CD4", "CC3", "CC4")),
            ("8.1", ("STEM5", "CD1", "CD4", "CPSAA2")),
            (
                "8.2",
                (
                    "CCL3", "STEM5", "CD4", "CPSAA2", "CPSAA5", "CC2", "CC3",
                ),
            ),
            ("8.3", ("STEM5", "CD3", "CC2", "CC3", "CE1")),
        ),
    ),
)
