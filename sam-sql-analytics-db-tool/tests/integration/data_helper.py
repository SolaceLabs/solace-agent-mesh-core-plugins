import sqlalchemy as sa
from datetime import datetime

metadata = sa.MetaData()

# Define tables using SQLAlchemy's generic types
users = sa.Table('users', metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('name', sa.String(100)),
    sa.Column('email', sa.String(100), unique=True),
    sa.Column('created_at', sa.DateTime)
)

categories = sa.Table('categories', metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('name', sa.String(100), unique=True)
)

products = sa.Table('products', metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('name', sa.String(100)),
    sa.Column('description', sa.Text),
    sa.Column('price', sa.Float)
)

product_categories = sa.Table('product_categories', metadata,
    sa.Column('product_id', sa.Integer, sa.ForeignKey('products.id', ondelete='CASCADE'), primary_key=True),
    sa.Column('category_id', sa.Integer, sa.ForeignKey('categories.id', ondelete='CASCADE'), primary_key=True)
)

orders = sa.Table('orders', metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE')),
    sa.Column('order_date', sa.Date),
    sa.Column('status', sa.String(50))
)

order_items = sa.Table('order_items', metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('order_id', sa.Integer, sa.ForeignKey('orders.id', ondelete='CASCADE')),
    sa.Column('product_id', sa.Integer, sa.ForeignKey('products.id', ondelete='CASCADE')),
    sa.Column('quantity', sa.Integer),
    sa.Column('price_per_unit', sa.Float)
)

reviews = sa.Table('reviews', metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('product_id', sa.Integer, sa.ForeignKey('products.id', ondelete='CASCADE')),
    sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE')),
    sa.Column('rating', sa.Integer),
    sa.Column('comment', sa.Text),
    sa.Column('created_at', sa.DateTime),
    sa.CheckConstraint('rating >= 1 AND rating <= 5')
)

# Table with PII data in columns that don't have obvious PII names
# This tests that PII detection works on content, not just column names
customer_records = sa.Table('customer_records', metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE')),
    sa.Column('account_notes', sa.Text),          # Contains phone numbers
    sa.Column('reference_code', sa.String(20)),   # Contains SSN-like patterns
    sa.Column('shipping_info', sa.Text),          # Contains full addresses
    sa.Column('transaction_metadata', sa.String(100)),  # Contains credit card numbers
    sa.Column('tracking_reference', sa.String(50)),      # Contains IP addresses
    sa.Column('contact_info', sa.String(100)),    # Contains email addresses (non-obvious name)
    sa.Column('external_links', sa.Text),         # Contains URLs
    sa.Column('account_holder', sa.String(100)),  # Contains person names (non-obvious)
    sa.Column('payment_account', sa.String(50))   # Contains IBAN/bank account numbers
)

def populate_db(engine):
    """Creates and populates a 7-table relational schema using a SQLAlchemy Engine."""
    # Drop and create tables
    with engine.begin() as conn:
        metadata.drop_all(conn, checkfirst=True)
        metadata.create_all(conn)

    # Insert data using SQLAlchemy's execute method in a new transaction
    with engine.begin() as conn:
        conn.execute(users.insert(), [
            {'id': 1, 'name': 'Alice Smith', 'email': 'alice@example.com', 'created_at': datetime(2023, 1, 10, 10, 0, 0)},
            {'id': 2, 'name': 'Bob Johnson', 'email': 'bob@example.com', 'created_at': datetime(2023, 1, 11, 11, 30, 0)},
            {'id': 3, 'name': 'Charlie Brown', 'email': 'charlie@example.com', 'created_at': datetime(2023, 1, 12, 14, 0, 0)},
            {'id': 4, 'name': 'Diana Prince', 'email': 'diana@example.com', 'created_at': datetime(2023, 1, 13, 16, 45, 0)},
            {'id': 5, 'name': 'Ethan Hunt', 'email': 'ethan@example.com', 'created_at': datetime(2023, 1, 14, 9, 0, 0)},
            {'id': 6, 'name': 'Fiona Glenanne', 'email': 'fiona@example.com', 'created_at': datetime(2023, 1, 15, 12, 15, 0)},
            {'id': 7, 'name': "George O'Malley", 'email': 'george@example.com', 'created_at': datetime(2023, 1, 16, 15, 30, 0)},
            {'id': 8, 'name': 'He-Man', 'email': 'heman@eternia.com', 'created_at': datetime(2023, 1, 17, 18, 0, 0)},
            {'id': 9, 'name': 'User With No Orders', 'email': 'no-orders@example.com', 'created_at': datetime(2023, 1, 18, 10, 0, 0)}
        ])

        conn.execute(categories.insert(), [
            {'id': 1, 'name': 'Electronics'}, {'id': 2, 'name': 'Books'}, {'id': 3, 'name': 'Home Goods'},
            {'id': 4, 'name': 'Apparel'}, {'id': 5, 'name': 'Toys'}, {'id': 6, 'name': 'Unused Category'}
        ])

        conn.execute(products.insert(), [
            {'id': 101, 'name': 'Laptop Pro 16"', 'description': 'A powerful laptop for professionals', 'price': 2399.99},
            {'id': 102, 'name': 'Smartphone Z', 'description': 'A latest model smartphone with great features', 'price': 999.50},
            {'id': 103, 'name': 'Wireless ANC Headphones', 'description': 'Noise-cancelling over-ear headphones', 'price': 249.99},
            {'id': 201, 'name': 'The Galactic Saga', 'description': 'A thrilling sci-fi adventure trilogy', 'price': 39.99},
            {'id': 202, 'name': 'History of Ancient Rome', 'description': 'A comprehensive look at Roman history', 'price': 55.00},
            {'id': 301, 'name': 'Espresso Machine', 'description': 'Brews cafe-quality espresso at home', 'price': 499.99},
            {'id': 401, 'name': 'Classic Denim Jacket', 'description': 'A comfortable and stylish denim jacket', 'price': 89.00},
            {'id': 501, 'name': 'Building Block Set', 'description': 'A 1500-piece set for endless creativity', 'price': 79.99},
            {'id': 104, 'name': '4K Webcam', 'description': 'High-definition webcam for streaming', 'price': 129.00},
            {'id': 302, 'name': 'Robotic Vacuum', 'description': 'Smart vacuum with mapping technology', 'price': 349.50},
            {'id': 999, 'name': 'Product with no category', 'description': 'An item that is not categorized', 'price': 10.00},
            {'id': 998, 'name': 'Product with NULL description', 'description': None, 'price': 19.99}
        ])

        conn.execute(product_categories.insert(), [
            {'product_id': 101, 'category_id': 1}, {'product_id': 102, 'category_id': 1},
            {'product_id': 103, 'category_id': 1}, {'product_id': 104, 'category_id': 1},
            {'product_id': 201, 'category_id': 2}, {'product_id': 202, 'category_id': 2},
            {'product_id': 301, 'category_id': 3}, {'product_id': 301, 'category_id': 1},
            {'product_id': 302, 'category_id': 3}, {'product_id': 302, 'category_id': 1},
            {'product_id': 401, 'category_id': 4}, {'product_id': 501, 'category_id': 5}
        ])

        conn.execute(orders.insert(), [
            {'id': 1001, 'user_id': 1, 'order_date': datetime(2023, 2, 15).date(), 'status': 'Shipped'},
            {'id': 1002, 'user_id': 2, 'order_date': datetime(2023, 2, 16).date(), 'status': 'Processing'},
            {'id': 1003, 'user_id': 1, 'order_date': datetime(2023, 2, 17).date(), 'status': 'Delivered'},
            {'id': 1004, 'user_id': 3, 'order_date': datetime(2023, 2, 18).date(), 'status': 'Shipped'},
            {'id': 1005, 'user_id': 4, 'order_date': datetime(2023, 2, 19).date(), 'status': 'Delivered'},
            {'id': 1006, 'user_id': 5, 'order_date': datetime(2023, 2, 20).date(), 'status': 'Cancelled'},
            {'id': 1007, 'user_id': 1, 'order_date': datetime(2023, 2, 21).date(), 'status': 'Shipped'},
            {'id': 1008, 'user_id': 6, 'order_date': datetime(2023, 2, 22).date(), 'status': 'Delivered'},
            {'id': 1009, 'user_id': 7, 'order_date': datetime(2023, 2, 23).date(), 'status': 'Processing'},
            {'id': 1010, 'user_id': 8, 'order_date': datetime(2023, 2, 24).date(), 'status': 'Shipped'}
        ])

        conn.execute(order_items.insert(), [
            {'id': 501, 'order_id': 1001, 'product_id': 101, 'quantity': 1, 'price_per_unit': 2399.99},
            {'id': 502, 'order_id': 1001, 'product_id': 103, 'quantity': 1, 'price_per_unit': 249.99},
            {'id': 503, 'order_id': 1002, 'product_id': 102, 'quantity': 1, 'price_per_unit': 999.50},
            {'id': 504, 'order_id': 1003, 'product_id': 301, 'quantity': 1, 'price_per_unit': 499.99},
            {'id': 505, 'order_id': 1003, 'product_id': 201, 'quantity': 1, 'price_per_unit': 39.99},
            {'id': 506, 'order_id': 1004, 'product_id': 401, 'quantity': 3, 'price_per_unit': 89.00},
            {'id': 507, 'order_id': 1005, 'product_id': 202, 'quantity': 1, 'price_per_unit': 55.00},
            {'id': 508, 'order_id': 1007, 'product_id': 104, 'quantity': 2, 'price_per_unit': 129.00},
            {'id': 509, 'order_id': 1008, 'product_id': 501, 'quantity': 1, 'price_per_unit': 79.99},
            {'id': 510, 'order_id': 1009, 'product_id': 102, 'quantity': 1, 'price_per_unit': 999.50},
            {'id': 511, 'order_id': 1009, 'product_id': 401, 'quantity': 1, 'price_per_unit': 89.00},
            {'id': 512, 'order_id': 1010, 'product_id': 999, 'quantity': 10, 'price_per_unit': 10.00}
        ])

        conn.execute(reviews.insert(), [
            {'id': 701, 'product_id': 101, 'user_id': 1, 'rating': 5, 'comment': 'Amazing laptop! Worth every penny.', 'created_at': datetime(2023, 3, 1, 12, 0, 0)},
            {'id': 702, 'product_id': 102, 'user_id': 2, 'rating': 5, 'comment': 'Best phone I have ever owned. 10/10!', 'created_at': datetime(2023, 3, 3, 9, 0, 0)},
            {'id': 703, 'product_id': 201, 'user_id': 1, 'rating': 4, 'comment': 'Great read, but the ending was a bit rushed.', 'created_at': datetime(2023, 3, 2, 15, 0, 0)},
            {'id': 704, 'product_id': 301, 'user_id': 3, 'rating': 5, 'comment': 'Makes perfect coffee and looks great on the counter.', 'created_at': datetime(2023, 3, 5, 10, 30, 0)},
            {'id': 705, 'product_id': 401, 'user_id': 4, 'rating': 3, 'comment': 'Good quality shirt, but it shrunk a little in the wash.', 'created_at': datetime(2023, 3, 6, 18, 0, 0)},
            {'id': 706, 'product_id': 101, 'user_id': 3, 'rating': 4, 'comment': 'Solid performance, but battery life could be better.', 'created_at': datetime(2023, 3, 7, 11, 0, 0)},
            {'id': 707, 'product_id': 501, 'user_id': 6, 'rating': 5, 'comment': 'My kids love this! Endless hours of fun.', 'created_at': datetime(2023, 3, 8, 14, 0, 0)},
            {'id': 708, 'product_id': 202, 'user_id': 5, 'rating': 2, 'comment': 'Very dry and academic. Not what I was expecting.', 'created_at': datetime(2023, 3, 9, 20, 0, 0)},
            {'id': 709, 'product_id': 103, 'user_id': 1, 'rating': 5, 'comment': 'Incredible sound quality and noise cancellation.', 'created_at': datetime(2023, 3, 10, 13, 20, 0)},
            {'id': 710, 'product_id': 999, 'user_id': 8, 'rating': 1, 'comment': 'Item broke immediately. 0/10 would not recommend. "By the power of Grayskull!" this is bad.', 'created_at': datetime(2023, 3, 11, 22, 0, 0)}
        ])

        # Insert PII data with non-obvious column names to test PII detection
        conn.execute(customer_records.insert(), [
            {
                'id': 1, 'user_id': 1,
                'account_notes': 'Customer prefers contact at 415-555-0123',
                'reference_code': '123-45-6789',
                'shipping_info': '123 Main Street, San Francisco, CA 94102',
                'transaction_metadata': 'Card: 4532-1234-5678-9010',
                'tracking_reference': '192.168.1.100',
                'contact_info': 'john.smith@company.com',
                'external_links': 'https://customer-portal.example.com/account/12345',
                'account_holder': 'John Michael Smith',
                'payment_account': 'GB82WEST12345698765432'
            },
            {
                'id': 2, 'user_id': 2,
                'account_notes': 'Call mobile: 650-555-9876 for delivery',
                'reference_code': '987-65-4321',
                'shipping_info': '456 Oak Avenue, Palo Alto, CA 94301',
                'transaction_metadata': 'Payment via 5425-2334-3010-9877',
                'tracking_reference': '10.0.0.42',
                'contact_info': 'sarah.jones@email.net',
                'external_links': 'http://tracking.fedex.com/track?id=987654321',
                'account_holder': 'Sarah Elizabeth Jones',
                'payment_account': 'DE89370400440532013000'
            },
            {
                'id': 3, 'user_id': 3,
                'account_notes': 'Best time to reach: (408) 555-1234',
                'reference_code': '456-78-9012',
                'shipping_info': '789 Wellington Street, Ottawa, ON K1A 0A9',
                'transaction_metadata': 'CC ending 6543',
                'tracking_reference': '172.16.254.1',
                'contact_info': 'michael.brown@domain.org',
                'external_links': 'https://www.linkedin.com/in/michaelbrown',
                'account_holder': 'Michael Robert Brown',
                'payment_account': 'FR1420041010050500013M02606'
            },
            {
                'id': 4, 'user_id': 4,
                'account_notes': 'Primary: 510-555-4567, Secondary: 925-555-8901',
                'reference_code': '234-56-7890',
                'shipping_info': '321 Yonge Street, Toronto, ON M5B 1R7',
                'transaction_metadata': 'Visa 4111-1111-1111-1111',
                'tracking_reference': '192.0.2.146',
                'contact_info': 'emily.davis@webmail.com',
                'external_links': 'https://github.com/emilydavis/projects',
                'account_holder': 'Emily Anne Davis',
                'payment_account': 'IT60X0542811101000000123456'
            },
            {
                'id': 5, 'user_id': 5,
                'account_notes': 'Work phone: 408-555-3210',
                'reference_code': '345-67-8901',
                'shipping_info': '654 Maple Drive, Sunnyvale, CA 94085',
                'transaction_metadata': 'MC 5555-5555-5555-4444',
                'tracking_reference': '198.51.100.22',
                'contact_info': 'david.wilson@business.co',
                'external_links': 'https://myaccount.aws.amazon.com/console',
                'account_holder': 'David James Wilson',
                'payment_account': 'ES9121000418450200051332'
            },
            {
                'id': 6, 'user_id': 6,
                'account_notes': 'Contact via 831-555-6789',
                'reference_code': '567-89-0123',
                'shipping_info': '987 Rideau Street, Ottawa, ON K1N 8S7',
                'transaction_metadata': 'Amex 3782-822463-10005',
                'tracking_reference': '203.0.113.88',
                'contact_info': 'jennifer.taylor@mail.com',
                'external_links': 'http://secure-banking.example.com/login',
                'account_holder': 'Jennifer Marie Taylor',
                'payment_account': 'NL91ABNA0417164300'
            },
            {
                'id': 7, 'user_id': 7,
                'account_notes': 'Leave message at 707-555-2345',
                'reference_code': '678-90-1234',
                'shipping_info': '147 King Street West, Toronto, ON M5H 1J9',
                'transaction_metadata': 'Card 6011-1111-1111-1117',
                'tracking_reference': '2001:0db8:85a3::8a2e:0370:7334',
                'contact_info': 'robert.anderson@provider.net',
                'external_links': 'https://dashboard.stripe.com/payments',
                'account_holder': 'Robert Christopher Anderson',
                'payment_account': 'BE68539007547034'
            },
            {
                'id': 8, 'user_id': 8,
                'account_notes': 'Eternia delivery hotline: 555-POWER (555-769-3700)',
                'reference_code': '789-01-2345',
                'shipping_info': 'Castle Grayskull, Eternia, Universe 94999',
                'transaction_metadata': 'Power Sword Credits 9999-8888-7777-6666',
                'tracking_reference': 'fe80::1',
                'contact_info': 'he-man@masters.eternia',
                'external_links': 'https://castle-grayskull.eternia/secrets',
                'account_holder': 'Adam Prince of Eternia',
                'payment_account': 'ET1234567890POWEROFGRAYSKULL'
            }
        ])
