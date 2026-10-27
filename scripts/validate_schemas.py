#!/usr/bin/env python3
"""Validate shared schemas are importable and consistent."""
import sys
sys.path.insert(0, '.')

from datetime import datetime, timezone
from shared.schemas import (
    Incident,
    Recovery,
    Evaluation,
    Requirement,
    EpisodeStartedEvent,
    RewardObservedEvent,
    EpisodeEndedEvent,
    SourceComponent,
    SCHEMA_VERSION,
    new_uuid,
)
from shared.schemas.contracts import RecoveryStatus, IncidentStatus
from shared.schemas.requirements import RequirementSource, RequirementType

# Basic instantiation tests
_ = Incident(run_id='r1', violation_type='test')
_ = Requirement(id='req1', title='Goal reward', description='test', requirement_type=RequirementType.reward, source=RequirementSource.developer_confirmed)
_ = EpisodeStartedEvent(schema_version=SCHEMA_VERSION,event_id=new_uuid(),event_type='episode_started',run_id='r1',episode_id='e1',environment_id='w',environment_version='v1',source_component=SourceComponent.ENVIRONMENT,payload={'seed':1})
_ = RewardObservedEvent(schema_version=SCHEMA_VERSION,event_id=new_uuid(),event_type='reward_observed',run_id='r1',episode_id='e1',timestep=1,environment_version='v1',source_component=SourceComponent.ENVIRONMENT,payload={'actual_reward':1.0})
_ = EpisodeEndedEvent(schema_version=SCHEMA_VERSION,event_id=new_uuid(),event_type='episode_ended',run_id='r1',episode_id='e1',environment_id='w',environment_version='v1',source_component=SourceComponent.ENVIRONMENT,payload={'total_reward':1.0,'steps':1,'terminated':False,'truncated':False,'success':False})
print('shared schemas ok')
