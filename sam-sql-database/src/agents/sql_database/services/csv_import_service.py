"""Service for importing CSV files into database tables."""

import os
import csv
from typing import List, Dict, Any, Optional
import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy import text, inspect

from solace_ai_connector.common.log import log


class CsvImportService:
    """Service for importing CSV files into database tables."""

    def __init__(self, engine: Engine):
        """Initialize the CSV import service.
        
        Args:
            engine: SQLAlchemy engine instance
        """
        self.engine = engine

    def import_csv_files(self, files: Optional[List[str]] = None, 
                        directories: Optional[List[str]] = None) -> None:
        """Import CSV files into database tables.
        
        Args:
            files: List of CSV file paths
            directories: List of directory paths containing CSV files
        """
        if not files:
            files = []
        elif isinstance(files, str):
            files = [file.strip() for file in files.split(',')]
        if not directories:
            directories = []
        elif isinstance(directories, str):
            directories = [directory.strip() for directory in directories.split(',')]

        # Collect all CSV files
        csv_files = []
        csv_files.extend(files or [])
        
        # Add files from directories
        for directory in directories or []:
            if os.path.isdir(directory):
                for filename in os.listdir(directory):
                    if filename.lower().endswith('.csv'):
                        csv_files.append(os.path.join(directory, filename))

        # Process each CSV file
        for csv_file in csv_files:
            try:
                self._import_csv_file(csv_file)
            except Exception as e:
                log.error("Error importing CSV file %s: %s", csv_file, str(e))


    @staticmethod
    def convert_headers_to_snake_case(headers: List[str]) -> List[str]:
        """Convert a list of headers to snake_case.

        Args:
            headers: List of header strings

        Returns:
            List of converted header strings
        """
        converted_headers = []

        for header in headers:
            header = header.strip().replace(' ', '_')  # replace spaces with underscores
            new_header = ""
            if "_" in header:  # assume it is already in snake_case
                new_header += header.lower()
            else:  # do reformat to snake_case
                for c in header:
                    if c.isupper():
                        new_header += "_" + c.lower()
                    else:
                        new_header += c
                new_header = new_header.lstrip('_')
            converted_headers.append(new_header)

        return converted_headers

    def _import_csv_file(self, file_path: str) -> None:
        """Import a single CSV file into a database table.
        
        Args:
            file_path: Path to CSV file
        """
        # Get table name from filename
        table_name = os.path.splitext(os.path.basename(file_path))[0].lower()
        table_name = ''.join(['_' + c.lower() if c.isupper() else c 
                            for c in table_name]).lstrip('_')

        # Check if table already exists
        if inspect(self.engine).has_table(table_name):
            log.info("Table %s already exists, skipping import", table_name)
            return

        try:
            # Read CSV headers and first row
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f, skipinitialspace=True) # remove spaces after commas
                headers = next(reader)
                
                # Convert headers to snake_case
                headers = self.convert_headers_to_snake_case(headers)

                # Create table
                columns = []
                has_id = False
                
                # Check if there's an id column
                for header in headers:
                    if header.lower() == 'id':
                        has_id = True
                        break

                # Add id column if none exists
                if not has_id:
                    columns.append(sa.Column('id', sa.Integer, primary_key=True))

                # Add columns for CSV fields
                for header in headers:
                    # If this is an id column, make it text type
                    if header.lower() == 'id':
                        columns.append(sa.Column(header, sa.Text))
                    else:
                        columns.append(sa.Column(header, sa.Text))

                # Create table
                metadata = sa.MetaData()
                table = sa.Table(table_name, metadata, *columns)
                metadata.create_all(self.engine)

                # Reset file pointer and skip header
                f.seek(0)
                next(reader)

                # Insert data in chunks
                chunk_size = 1000
                chunk = []
                
                for row in reader:
                    if len(row) != len(headers):
                        log.warning("Skipping row with incorrect number of columns in %s", 
                                  file_path)
                        continue

                    # Create row dict
                    row_dict = dict(zip(headers, row))
                    chunk.append(row_dict)

                    if len(chunk) >= chunk_size:
                        self._insert_chunk(table_name, chunk)
                        chunk = []

                # Insert remaining rows
                if chunk:
                    self._insert_chunk(table_name, chunk)

        except Exception as e:
            log.error("Error processing CSV file %s: %s", file_path, str(e))
            raise

    def _insert_chunk(self, table_name: str, chunk: List[Dict[str, Any]]) -> None:
        """Insert a chunk of rows into a table.
        
        Args:
            table_name: Name of the target table
            chunk: List of row dictionaries to insert
        """
        if not chunk:
            return

        try:
            with self.engine.begin() as conn:
                # Build insert statement
                insert_stmt = text(
                    f"INSERT INTO {table_name} ({', '.join(chunk[0].keys())}) "
                    f"VALUES ({', '.join([':' + k for k in chunk[0].keys()])})"
                )
                
                # Execute with chunk of rows
                conn.execute(insert_stmt, chunk)
        except Exception as e:
            log.error("Error inserting chunk into %s: %s", table_name, str(e))
            raise
