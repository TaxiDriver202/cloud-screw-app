from pydantic import BaseModel, Field


class RuuviTag(BaseModel):
    mac: str = Field(description="The MAC address of the tag")
    temperature: float
    humidity: float
    pressure: float


class GatewayData(BaseModel):
    tags: dict[str, RuuviTag]
    gwmac: str


class GatewayHTTPrequest(BaseModel):
    data: GatewayData


class StoredReading(BaseModel):
    """A row read back out of the `data` table."""

    mac: str
    temperature: float
    humidity: float
    pressure: float
    date: str
