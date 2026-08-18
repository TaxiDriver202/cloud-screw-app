from pydantic import BaseModel, Field


class RuuviTag(BaseModel):
    id: str = Field(description="The MAC address of the tag")
    temperature: float
    humidity: float
    pressure: float
    accelX: float | None = None
    accelY: float | None = None
    accelZ: float | None = None


class GatewayData(BaseModel):
    tags: dict[str, RuuviTag]
    gw_mac: str


class GatewayHTTPrequest(BaseModel):
    data: GatewayData


class StoredReading(BaseModel):
    """A row read back out of the `data` table."""

    mac: str
    temperature: float
    humidity: float
    pressure: float
    date: str
