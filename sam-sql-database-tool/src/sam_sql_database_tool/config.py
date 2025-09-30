from typing import Optional, Literal, Any
from pydantic import BaseModel, Field, model_validator, SecretStr

class DatabaseConfig(BaseModel):
    tool_name: str = Field(
        description="The name of the tool as it will be invoked by the LLM."
    )
    tool_description: Optional[str] = Field(
        default="", description="A description of what the tool does."
    )
    db_type: Literal["postgresql", "mysql", "sqlite"] = Field(
        description="Type of the database."
    )
    db_host: Optional[str] = Field(
        default=None, description="Database host (required for PostgreSQL/MySQL)."
    )
    db_port: Optional[int] = Field(
        default=None, description="Database port (required for PostgreSQL/MySQL)."
    )
    db_user: Optional[str] = Field(
        default=None, description="Database user (required for PostgreSQL/MySQL)."
    )
    db_password: Optional[SecretStr] = Field(
        default=None, description="Database password (required for PostgreSQL/MySQL)."
    )
    db_name: str = Field(
        description="Database name (for PostgreSQL/MySQL) or file path (for SQLite)."
    )

    @model_validator(mode='after')
    def check_required_fields(self) -> 'DatabaseConfig':
        if self.db_type in ["postgresql", "mysql"]:
            if not all([self.db_host, self.db_port, self.db_user, self.db_password]):
                raise ValueError(
                    f"For db_type '{self.db_type}', db_host, db_port, db_user, and db_password are required."
                )
        return self
    
    def get(self, key: str, default: Any = None) -> Any:
        """Allows dictionary-like access to the model's attributes."""
        return getattr(self, key, default)