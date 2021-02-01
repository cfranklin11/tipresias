"""added_team_table

Revision ID: 9790e4b6fcb3
Revises: 
Create Date: 2021-01-21 06:11:32.049591

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9790e4b6fcb3'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('teams',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.Enum('ADELAIDE', 'BRISBANE', 'CARLTON', 'COLLINGWOOD', 'ESSENDON', 'FITZROY', 'FREMANTLE', 'GEELONG', 'GOLD_COAST', 'GWS', 'HAWTHORN', 'MELBOURNE', 'NORTH_MELBOURNE', 'PORT_ADELAIDE', 'RICHMOND', 'ST_KILDA', 'SYDNEY', 'UNIVERSITY', 'WESTERN_BULLDOGS', 'WEST_COAST', name='teamname'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('teams')
    # ### end Alembic commands ###