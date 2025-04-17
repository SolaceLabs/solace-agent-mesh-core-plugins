#!/usr/bin/env python3
"""Test database setup script for sam-sql-database.

This script manages test database instances for the sam-sql-database agent.
It supports MySQL, PostgreSQL and SQLite databases with sample HR data.

Example usage:
    # Start a MySQL test database
    ./setup_test_db.py --type mysql start
    
    # Stop a PostgreSQL test database
    ./setup_test_db.py --type postgres stop
    
    # Cleanup SQLite test database
    ./setup_test_db.py --type sqlite cleanup
"""

import argparse
import logging
import os
import random
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Set SQLAlchemy logging to WARNING
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

# Test database configuration
DB_CONFIGS = {
    'mysql': {
        'container_name': 'sam-sql-test-mysql',
        'image': 'mysql:8.3',
        'port': 3306,
        'database': 'sam_test_hr',
        'user': 'sam_test_user',
        'password': 'sam_test_pass',
        'root_password': 'sam_test_root_pass',
    },
    'postgres': {
        'container_name': 'sam-sql-test-postgres',
        'image': 'postgres:16',
        'port': 5432,
        'database': 'sam_test_hr',
        'user': 'sam_test_user',
        'password': 'sam_test_pass',
    },
    'sqlite': {
        'database': 'sam_test_hr.db',
    }
}

# Sample data for HR database
DEPARTMENTS = [
    ('Engineering', 'Building A'),
    ('Sales', 'Building B'),
    ('Marketing', 'Building B'),
    ('HR', 'Building A'),
    ('Finance', 'Building C'),
]

JOB_TITLES = [
    'Software Engineer',
    'Senior Software Engineer',
    'Sales Representative',
    'Marketing Specialist',
    'HR Manager',
    'Financial Analyst',
    'Department Manager',
    'Team Lead',
]

FIRST_NAMES = [
    'James', 'Mary', 'John', 'Patricia', 'Robert', 'Jennifer',
    'Michael', 'Linda', 'William', 'Elizabeth', 'David', 'Barbara',
    'Richard', 'Susan', 'Joseph', 'Jessica', 'Thomas', 'Sarah',
    'Charles', 'Karen', 'Christopher', 'Nancy', 'Daniel', 'Lisa',
]

LAST_NAMES = [
    'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia',
    'Miller', 'Davis', 'Rodriguez', 'Martinez', 'Hernandez', 'Lopez',
    'Gonzalez', 'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore',
    'Jackson', 'Martin', 'Lee', 'Perez', 'Thompson', 'White',
]

def check_container_runtime() -> Tuple[Optional[str], Optional[str]]:
    """Check if Docker or Podman is available.
    
    Returns:
        Tuple of (runtime_cmd, runtime_name) or (None, None) if neither is available
    """
    try:
        # Check for Docker
        subprocess.run(['docker', 'info'], 
                     stdout=subprocess.DEVNULL, 
                     stderr=subprocess.DEVNULL, 
                     check=True)
        return 'docker', 'Docker'
    except (subprocess.CalledProcessError, FileNotFoundError):
        try:
            # Check for Podman
            subprocess.run(['podman', 'info'],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         check=True)
            return 'podman', 'Podman'
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None, None

def generate_sample_data(num_employees: int = 15) -> Tuple[List, List, List, List]:
    """Generate sample HR data.
    
    Args:
        num_employees: Number of employees to generate
        
    Returns:
        Tuple of (employees, departments, salaries, job_history)
    """
    # Generate departments
    departments = [(i + 1,) + dept for i, dept in enumerate(DEPARTMENTS)]
    
    # Generate employees and related data
    employees = []
    salaries = []
    job_history = []
    
    for emp_id in range(1, num_employees + 1):
        # Basic employee info
        first_name = random.choice(FIRST_NAMES)
        last_name = random.choice(LAST_NAMES)
        email = f"{first_name.lower()}.{last_name.lower()}@example.com"
        hire_date = datetime.now() - timedelta(days=random.randint(0, 3650))
        dept_id = random.randint(1, len(departments))
        
        employees.append((
            emp_id, first_name, last_name, email, 
            hire_date.strftime('%Y-%m-%d'), dept_id
        ))
        
        # Salary history
        current_salary = random.randint(50000, 150000)
        salary_start = hire_date
        salaries.append((
            emp_id, current_salary, 
            salary_start.strftime('%Y-%m-%d'), None
        ))
        
        # Job history
        num_positions = random.randint(1, 3)
        for pos in range(num_positions):
            start_date = hire_date + timedelta(days=pos * 365)
            end_date = None if pos == num_positions - 1 else start_date + timedelta(days=365)
            job_title = random.choice(JOB_TITLES)
            
            job_history.append((
                emp_id, job_title,
                start_date.strftime('%Y-%m-%d'),
                end_date.strftime('%Y-%m-%d') if end_date else None
            ))
    
    return employees, departments, salaries, job_history

def get_create_tables_sql(db_type: str) -> str:
    """Get SQL statements for creating the HR tables.
    
    Args:
        db_type: Database type (mysql, postgres, sqlite)
        
    Returns:
        SQL statements as string
    """
    # Adjust SQL syntax based on database type
    auto_increment = 'AUTO_INCREMENT' if db_type == 'mysql' else (
        'AUTOINCREMENT' if db_type == 'sqlite' else 'GENERATED BY DEFAULT AS IDENTITY'
    )
    
    return f"""
    CREATE TABLE departments (
        dept_id INTEGER PRIMARY KEY {auto_increment},
        dept_name VARCHAR(50) NOT NULL,
        location VARCHAR(50) NOT NULL
    );

    CREATE TABLE employees (
        emp_id INTEGER PRIMARY KEY {auto_increment},
        first_name VARCHAR(50) NOT NULL,
        last_name VARCHAR(50) NOT NULL,
        email VARCHAR(100) NOT NULL UNIQUE,
        hire_date DATE NOT NULL,
        dept_id INTEGER NOT NULL,
        FOREIGN KEY (dept_id) REFERENCES departments(dept_id)
    );

    CREATE TABLE salaries (
        emp_id INTEGER NOT NULL,
        salary INTEGER NOT NULL,
        start_date DATE NOT NULL,
        end_date DATE,
        FOREIGN KEY (emp_id) REFERENCES employees(emp_id)
    );

    CREATE TABLE job_history (
        emp_id INTEGER NOT NULL,
        job_title VARCHAR(100) NOT NULL,
        start_date DATE NOT NULL,
        end_date DATE,
        FOREIGN KEY (emp_id) REFERENCES employees(emp_id)
    );
    """


class TestDatabaseManager:
    """Manages test database lifecycle."""
    
    def __init__(self, db_type: str):
        """Initialize database manager.
        
        Args:
            db_type: Database type (mysql, postgres, sqlite)
        """
        if db_type not in DB_CONFIGS:
            raise ValueError(f"Unsupported database type: {db_type}")
        
        self.db_type = db_type
        self.config = DB_CONFIGS[db_type]
        self.runtime_cmd, self.runtime_name = check_container_runtime()
        self.started = False
        
        if db_type != 'sqlite' and not self.runtime_cmd:
            raise RuntimeError(
                "Neither Docker nor Podman is available. "
                "Please install one to use MySQL or PostgreSQL test databases."
            )
    
    def start(self):
        """Start the test database."""
        if self.db_type == 'sqlite':
            self._start_sqlite()
        else:
            self._start_container()
    
    def stop(self):
        """Stop the test database."""
        if self.db_type != 'sqlite':
            self._stop_container()
    
    def cleanup(self, remove_image: bool = False):
        """Clean up all test database resources.
        
        Args:
            remove_image: Whether to remove the container image
        """
        if self.db_type == 'sqlite':
            self._cleanup_sqlite()
        else:
            self._cleanup_container(remove_image)
    
    def _start_sqlite(self):
        """Initialize SQLite database."""
        import sqlite3
        
        db_path = os.path.abspath(self.config['database'])
        if os.path.exists(db_path):
            logging.info("SQLite database already exists at: %s", db_path)
            return
        
        logging.info("Creating SQLite database at: %s", db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create tables
        sql_statements = get_create_tables_sql('sqlite')
        logging.debug("Table creation SQL:\n%s", sql_statements)
        for statement in sql_statements.split(';'):
            if statement.strip():
                cursor.execute(statement)
        
        # Insert sample data
        employees, departments, salaries, job_history = generate_sample_data()
        
        cursor.executemany(
            "INSERT INTO departments (dept_id, dept_name, location) VALUES (?, ?, ?)",
            departments
        )
        cursor.executemany(
            "INSERT INTO employees (emp_id, first_name, last_name, email, hire_date, dept_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            employees
        )
        cursor.executemany(
            "INSERT INTO salaries (emp_id, salary, start_date, end_date) VALUES (?, ?, ?, ?)",
            salaries
        )
        cursor.executemany(
            "INSERT INTO job_history (emp_id, job_title, start_date, end_date) VALUES (?, ?, ?, ?)",
            job_history
        )
        
        conn.commit()
        conn.close()
        logging.info("SQLite database created successfully")
        self.started = True
    
    def _cleanup_sqlite(self):
        """Remove SQLite database file."""
        db_path = self.config['database']
        if os.path.exists(db_path):
            os.remove(db_path)
            logging.info("SQLite database removed")
    
    def _start_container(self):
        """Start database container and initialize schema."""
        container_name = self.config['container_name']
        
        # Check if container already exists
        result = subprocess.run(
            [self.runtime_cmd, 'ps', '-a', '-q', '-f', f'name={container_name}'],
            capture_output=True,
            text=True
        )
        
        if result.stdout.strip():
            logging.debug("Container already exists, starting it")
            subprocess.run([self.runtime_cmd, 'start', container_name], check=True)
            return
        
        # Create and start container
        volume_name = f"{container_name}-vol"
        cmd = [
            self.runtime_cmd, 'run',
            '--name', container_name,
            '-d',
            '-p', f'{self.config["port"]}:{self.config["port"]}',
            '-v', f'{volume_name}:/var/lib/mysql' if self.db_type == 'mysql' else f'{volume_name}:/var/lib/postgresql/data',
        ]
        
        # Add environment variables
        if self.db_type == 'mysql':
            cmd.extend([
                '-e', f'MYSQL_DATABASE={self.config["database"]}',
                '-e', f'MYSQL_USER={self.config["user"]}',
                '-e', f'MYSQL_PASSWORD={self.config["password"]}',
                '-e', f'MYSQL_ROOT_PASSWORD={self.config["root_password"]}',
            ])
        else:  # postgres
            cmd.extend([
                '-e', f'POSTGRES_DB={self.config["database"]}',
                '-e', f'POSTGRES_USER={self.config["user"]}',
                '-e', f'POSTGRES_PASSWORD={self.config["password"]}',
                '-e', 'POSTGRES_HOST_AUTH_METHOD=md5',
                # Configure authentication for all hosts
                '-e', 'POSTGRES_INITDB_ARGS=--auth-host=md5',
            ])
        
        cmd.append(self.config['image'])
        subprocess.run(cmd, check=True)
        
        # Wait for database to be ready
        logging.info("Waiting for database to be ready...")
        time.sleep(30)  # Simple wait for now
        
        # Initialize schema and data
        if self.db_type == 'mysql':
            self._init_mysql()
        else:
            self._init_postgres()
    
    def _stop_container(self):
        """Stop the database container."""
        container_name = self.config['container_name']
        subprocess.run([self.runtime_cmd, 'stop', container_name], check=True)
        logging.info("Database container stopped")
    
    def _cleanup_container(self, remove_image: bool = False):
        """Remove container, volume, and optionally the image.
        
        Args:
            remove_image: Whether to remove the container image
        """
        container_name = self.config['container_name']
        volume_name = f"{container_name}-vol"
        
        # Remove container if it exists
        subprocess.run(
            [self.runtime_cmd, 'rm', '-f', container_name],
            stderr=subprocess.DEVNULL
        )
        
        # Remove volume if it exists
        subprocess.run(
            [self.runtime_cmd, 'volume', 'rm', '-f', volume_name],
            stderr=subprocess.DEVNULL
        )
        
        if remove_image:
            # Remove image
            subprocess.run(
                [self.runtime_cmd, 'rmi', '-f', self.config['image']],
                stderr=subprocess.DEVNULL
            )
            logging.info("Database container, volume, and image removed")
        else:
            logging.info("Database container and volume removed")
    
    def _print_connection_info(self):
        """Print database connection information."""
        if self.db_type == 'sqlite':
            logging.info("\nDatabase connection information:")
            logging.info("Type: SQLite")
            logging.info("Database file: %s", os.path.abspath(self.config['database']))
        else:
            logging.info("\nDatabase connection information:")
            logging.info("Type: %s", self.db_type.upper())
            logging.info("Host: localhost")
            logging.info("Port: %d", self.config['port'])
            logging.info("Database: %s", self.config['database'])
            logging.info("User: %s", self.config['user'])
            logging.info("Password: %s", self.config['password'])
            if self.db_type == 'mysql':
                logging.info("Root Password: %s", self.config['root_password'])

    def _init_mysql(self):
        """Initialize MySQL schema and sample data."""
        # Create SQL file
        sql_file = 'init.sql'
        with open(sql_file, 'w') as f:
            # Create tables
            sql_statements = get_create_tables_sql('mysql')
            logging.debug("Table creation SQL:\n%s", sql_statements)
            f.write(sql_statements)
            
            # Insert sample data
            employees, departments, salaries, job_history = generate_sample_data()
            
            # Write INSERT statements
            for dept in departments:
                # Convert tuple to list for modification
                dept_list = list(dept)
                values = ", ".join(
                    f"'{v}'" if isinstance(v, str) else
                    str(v) if v is not None else "NULL"
                    for v in dept_list
                )
                sql = f"INSERT INTO departments (dept_id, dept_name, location) VALUES ({values});"
                logging.debug("SQL: %s", sql)
                f.write(sql + "\n")
            
            for emp in employees:
                emp_list = list(emp)
                values = ", ".join(
                    f"'{v}'" if isinstance(v, str) else
                    str(v) if v is not None else "NULL"
                    for v in emp_list
                )
                f.write(
                    f"INSERT INTO employees (emp_id, first_name, last_name, email, hire_date, dept_id) "
                    f"VALUES ({values});\n"
                )
            
            for salary in salaries:
                salary_list = list(salary)
                values = ", ".join(
                    f"'{v}'" if isinstance(v, str) else
                    str(v) if v is not None else "NULL"
                    for v in salary_list
                )
                f.write(
                    f"INSERT INTO salaries (emp_id, salary, start_date, end_date) "
                    f"VALUES ({values});\n"
                )
            
            for job in job_history:
                job_list = list(job)
                values = ", ".join(
                    f"'{v}'" if isinstance(v, str) else
                    str(v) if v is not None else "NULL"
                    for v in job_list
                )
                f.write(
                    f"INSERT INTO job_history (emp_id, job_title, start_date, end_date) "
                    f"VALUES ({values});\n"
                )
        
        # Copy SQL file to container
        container_name = self.config['container_name']
        subprocess.run(
            [self.runtime_cmd, 'cp', sql_file, f'{container_name}:/init.sql'],
            check=True
        )
        
        # Execute SQL file
        subprocess.run([
            self.runtime_cmd, 'exec', container_name,
            'mysql', 
            f'-u{self.config["user"]}',
            f'-p{self.config["password"]}',
            self.config['database'],
            '-e', f'source /init.sql'
        ], check=True)
        
        # Clean up SQL file
        os.remove(sql_file)
        logging.info("MySQL database initialized with sample data")
        self.started = True
    
    def _init_postgres(self):
        """Initialize PostgreSQL schema and sample data."""
        # Create SQL file
        sql_file = 'init.sql'
        with open(sql_file, 'w') as f:
            # Create tables
            sql_statements = get_create_tables_sql('postgres')
            logging.debug("Table creation SQL:\n%s", sql_statements)
            f.write(sql_statements)
            
            # Insert sample data
            employees, departments, salaries, job_history = generate_sample_data()
            
            # Write INSERT statements
            for dept in departments:
                # Convert tuple to list for modification
                dept_list = list(dept)
                values = ", ".join(
                    f"'{v}'" if isinstance(v, str) else
                    str(v) if v is not None else "NULL"
                    for v in dept_list
                )
                sql = f"INSERT INTO departments (dept_id, dept_name, location) VALUES ({values});"
                logging.debug("SQL: %s", sql)
                f.write(sql + "\n")
            
            for emp in employees:
                emp_list = list(emp)
                values = ", ".join(
                    f"'{v}'" if isinstance(v, str) else
                    str(v) if v is not None else "NULL"
                    for v in emp_list
                )
                f.write(
                    f"INSERT INTO employees (emp_id, first_name, last_name, email, hire_date, dept_id) "
                    f"VALUES ({values});\n"
                )
            
            for salary in salaries:
                salary_list = list(salary)
                values = ", ".join(
                    f"'{v}'" if isinstance(v, str) else
                    str(v) if v is not None else "NULL"
                    for v in salary_list
                )
                f.write(
                    f"INSERT INTO salaries (emp_id, salary, start_date, end_date) "
                    f"VALUES ({values});\n"
                )
            
            for job in job_history:
                job_list = list(job)
                values = ", ".join(
                    f"'{v}'" if isinstance(v, str) else
                    str(v) if v is not None else "NULL"
                    for v in job_list
                )
                f.write(
                    f"INSERT INTO job_history (emp_id, job_title, start_date, end_date) "
                    f"VALUES ({values});\n"
                )
        
        # Copy SQL file to container
        container_name = self.config['container_name']
        subprocess.run(
            [self.runtime_cmd, 'cp', sql_file, f'{container_name}:/init.sql'],
            check=True
        )
        
        # Execute SQL file
        subprocess.run([
            self.runtime_cmd, 'exec', container_name,
            'bash', '-c',
            f"psql -U {self.config['user']} -d {self.config['database']} -f /init.sql"
        ], check=True)
        
        # Clean up SQL file
        os.remove(sql_file)
        logging.info("PostgreSQL database initialized with sample data")
        self.started = True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Setup test database for sam-sql-database agent.'
    )
    parser.add_argument(
        '--type', '-t',
        type=str,
        required=True,
        help='Comma-separated list of database types (mysql,postgres,sqlite)'
    )
    parser.add_argument(
        'action',
        choices=['start', 'stop', 'cleanup', 'restart'],
        help='Action to perform'
    )
    parser.add_argument(
        '--remove-image',
        action='store_true',
        help='Remove container image during cleanup (default: False)'
    )
    
    args = parser.parse_args()
    
    try:
        db_types = [t.strip() for t in args.type.split(',')]
        invalid_types = [t for t in db_types if t not in ['mysql', 'postgres', 'sqlite']]
        if invalid_types:
            raise ValueError(f"Invalid database type(s): {', '.join(invalid_types)}")
            
        for db_type in db_types:
            manager = TestDatabaseManager(db_type)
            logging.info("\nManaging %s database:", db_type.upper())
            
            if args.action == 'stop' or args.action == 'cleanup':
                manager = TestDatabaseManager(db_type)
                if args.action == 'stop':
                    manager.stop()
                else:  # cleanup
                    manager.cleanup(args.remove_image)
        
        # Print connection info for all started databases
        if args.action in ('start', 'restart'):
            logging.info("\nConnection information for all started databases:")
            # Keep track of managers to access their started state
            managers = {}
            for db_type in db_types:
                managers[db_type] = TestDatabaseManager(db_type)
                
            for db_type in db_types:
                manager = managers[db_type]
                if args.action == 'start':
                    manager.start()
                elif args.action == 'restart':
                    manager.cleanup(args.remove_image)
                    manager.start()
                
            # Print connection info for started databases
            for db_type, manager in managers.items():
                if manager.started:
                    manager._print_connection_info()
            
    except Exception as e:
        logging.error(str(e))
        sys.exit(1)


if __name__ == '__main__':
    main()
