from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NivelCriticidad(StrEnum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"


class ExtraccionTecnica(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tecnologias: list[str] = Field(
        min_length=1,
        description="Tecnologías, lenguajes, frameworks, bases de datos o servicios mencionados en el texto, con su nombre oficial.",
    )
    nivel_de_criticidad: NivelCriticidad = Field(
        description="Criticidad del problema o del sistema descrito: baja, media o alta.",
    )
    resumen_tecnico: str = Field(
        min_length=20,
        max_length=400,
        description="Resumen técnico de una o dos oraciones en español.",
    )

    @field_validator("tecnologias")
    @classmethod
    def validar_tecnologias(cls, valores: list[str]) -> list[str]:
        limpias = []
        for valor in valores:
            nombre = valor.strip()
            if nombre and nombre.lower() not in {t.lower() for t in limpias}:
                limpias.append(nombre)
        if not limpias:
            raise ValueError("La lista de tecnologías no puede estar vacía")
        return limpias

    @field_validator("resumen_tecnico")
    @classmethod
    def validar_resumen(cls, valor: str) -> str:
        return " ".join(valor.split())
