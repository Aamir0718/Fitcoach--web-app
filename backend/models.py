# models.py
import json

class UserProfile:
    def __init__(self, name=None, age=None, gender=None, height=None, weight=None,
                 goal=None, level=None, workout_place=None, injuries=None,
                 days_per_week=None, plays_sport=False, sport=None, sport_profile=None):
        self.name = name
        self.age = age
        self.gender = gender
        self.height = height
        self.weight = weight
        self.goal = goal
        self.level = level
        self.workout_place = workout_place
        self.injuries = injuries
        self.days_per_week = days_per_week
        self.plays_sport = plays_sport
        self.sport = sport
        self.sport_profile = sport_profile  # dict with sport-specific answers

    def to_dict(self):
        sp = self.sport_profile
        if isinstance(sp, str):
            try: sp = json.loads(sp)
            except: sp = {}
        return {
            "name": self.name, "age": self.age, "gender": self.gender,
            "height": self.height, "weight": self.weight, "goal": self.goal,
            "level": self.level, "workout_place": self.workout_place,
            "injuries": self.injuries, "days_per_week": self.days_per_week,
            "plays_sport": self.plays_sport, "sport": self.sport,
            "sport_profile": sp or {}
        }