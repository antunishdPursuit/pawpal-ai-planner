from datetime import time
from types import SimpleNamespace
import re
import pytest

from calendar_presentation import CalendarItem, render_timeline
from ui_components import calendar_item


def test_task_labels_are_escaped_and_tones_are_not_injected():
    html = render_timeline(['<Mon>'], [[CalendarItem('<script>walk</script>', 540,
        pet='Luna & Miso', owner='"Taylor"', location='<park>', tone='" onmouseover="oops')]])
    assert '<script>' not in html and 'onmouseover=' not in html
    assert '&lt;script&gt;walk&lt;/script&gt;' in html
    assert 'Luna &amp; Miso' in html and '&quot;Taylor&quot;' in html
    assert '&lt;Mon&gt; timed tasks' in html


def test_overlapping_display_blocks_get_separate_lanes_without_dropping_tasks():
    items = [CalendarItem('Walk', 540), CalendarItem('Brush', 540), CalendarItem('Feed', 570)]
    html = render_timeline(['Monday'], [items])
    assert html.count('class="paw-calendar-event paw-time-event') == 3
    assert 'left:calc(0.000000%' in html
    assert 'left:calc(33.333333%' in html
    assert 'left:calc(66.666667%' in html
    assert all(title in html for title in ('Walk', 'Brush', 'Feed'))


def test_anytime_is_separate_and_all_items_remain_visible_to_assistive_tools():
    items = [CalendarItem(f'Care {i}', 540 + i * 60) for i in range(5)]
    items.append(CalendarItem('Fresh water', None, projected=True))
    html = render_timeline(['Monday'], [items])
    assert 'Monday Anytime tasks' in html
    assert 'paw-anytime-event' in html and 'Fresh water' in html
    assert 'Planned repeat' in html
    assert html.count('<article') == 6


def test_midnight_and_late_night_stay_inside_the_rendered_day_range():
    html = render_timeline(['Tuesday'], [[CalendarItem('Early', 0), CalendarItem('Late', 1439)]])
    assert '--paw-calendar-hours:24' in html
    assert '12:00 AM' in html and '11:59 PM' in html
    offsets = [float(value) for value in re.findall(r'<article[^>]*top:calc\(([\d.]+) \*', html)]
    assert min(offsets) == 0 and max(offsets) < 24
    assert '11:59 PM –' not in html  # No invented end time/duration.


def test_projection_uses_the_existing_viewer_zone_clock_and_status():
    task = SimpleNamespace(title='Walk', time_of_day=time(8), location_text='Park')
    entry = SimpleNamespace(task=task, display_time=time(9, 30), owner_name='Taylor', projected=True, status='pending')
    item = calendar_item(entry, SimpleNamespace(name='Luna', pet_id=2))
    assert item.minute == 570 and item.owner == 'Taylor' and item.projected
    html = render_timeline(['Wednesday'], [[item]])
    assert '9:30 AM' in html and '8:00 AM' not in html
    assert 'projected' in html and 'Luna / Taylor' in html


def test_empty_week_and_completed_tasks_have_meaningful_structure():
    html = render_timeline([str(i) for i in range(7)], [[] for _ in range(7)])
    assert html.count('class="paw-day-track"') == 7
    assert '<article' not in html and 'No tasks' not in html
    done = render_timeline(['Thursday'], [[CalendarItem('Walk', 540, status='done')]])
    assert 'done' in done and 'Done' in done


def test_invalid_or_clipping_ranges_are_rejected():
    with pytest.raises(ValueError):
        render_timeline(['Friday'], [[CalendarItem('Late', 1500)]])
    with pytest.raises(ValueError):
        render_timeline(['Friday'], [[CalendarItem('Early', 60)]], start_hour=8, end_hour=10)
