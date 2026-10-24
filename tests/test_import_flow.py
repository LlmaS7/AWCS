"""Offline import regression using the real controller; only extraction is scripted."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch
from uuid import uuid4

from ai.configuration import Configuration
from ai.service import AIService
from controller import Controller
from simulation import Simulation


class ExtractionProvider:
    def chat(self, cfg, messages, tools, token):
        token.check()
        content = json.loads(messages[-1]['content'])
        proposal = {'candidates': [{
            'source_ids': [content['blocks'][0]['id']],
            'pickup_id': content['locations']['pickup'][0]['id'],
            'delivery_id': content['locations']['delivery'][0]['id'],
            'quantity_kind': 'trips', 'count': 3,
        }], 'excluded': []}
        return {'tool_calls': [{'function': {
            'name': 'propose_import_draft', 'arguments': json.dumps(proposal),
        }}]}, {}


class ImportFlowTests(unittest.TestCase):
    def test_analysis_then_partial_and_full_creation_with_idempotent_retry(self):
        definition = dict(format='sditadc-map', version=1, name='Import regression',
            grid=dict(width=9, height=9, rows=['#########'] + ['#.......#'] * 7 + ['#########']),
            points=dict(starts=[[1, 1]], parking=[[1, 1], [7, 1], [7, 7]],
                        pickups=[[2, 4]], deliveries=[[6, 4]]),
            robots=dict(default_count=1, max_count=1), random_obstacles=dict(count=0))
        sim = Simulation(7, initial_tasks=0, map_id='import-test', map_definition=definition, robot_count=1)
        with patch('controller.Simulation', return_value=sim):
            controller = Controller(paused=True)
        self.addCleanup(controller.stop, save_on_exit=False)
        controller.start()
        temporary = TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(temporary.cleanup)
        configuration = Configuration(path=Path(temporary.name) / 'settings.json')
        configuration.save(dict(api_key='synthetic-local-only', model='scripted', remember=False))
        ai = AIService(controller, configuration, ExtractionProvider())
        self.addCleanup(ai.close)

        def complete(action):
            finished = Event()
            original = ai.emit
            cursor = ai.serial
            def emit(kind, **data):
                original(kind, **data)
                if kind == 'done':
                    finished.set()
            with patch.object(ai, 'emit', side_effect=emit):
                result = action()
                self.assertTrue(finished.wait(15), 'Import request did not finish')
            events = ai.event_page(cursor)['events']
            self.assertFalse([e for e in events if e['kind'] == 'error'], events)
            return result

        upload = ai.imports.upload('orders.txt', b'Move three trips from pickup 1 to delivery 1.', controller.generation)['draft']
        complete(lambda: ai.launch('import_extract', dict(document_id=upload['document_id'], generation=controller.generation)))
        self.assertEqual(len(controller.state()['tasks']), 0, 'Analysis must not create tasks')
        ready = ai.imports.draft()['draft']
        self.assertEqual(ready['state'], 'ready')
        confirmation = dict(draft_id=ready['draft_id'], expected_revision=ready['revision'],
                            confirmation_id=uuid4().hex, selections=[dict(candidate_id='c1', count=2)])
        complete(lambda: ai.imports.commit(confirmation))
        partial = ai.imports.draft()['draft']
        self.assertEqual(partial['candidates'][0]['created_count'], 2)
        self.assertEqual(partial['candidates'][0]['remaining'], 1)
        self.assertTrue(partial['candidates'][0]['ready'])
        self.assertEqual(ai.imports.commit(confirmation)['status'], 'finished')
        self.assertEqual(len(controller.state()['tasks']), 2, 'Retry must not duplicate tasks')
        complete(lambda: ai.imports.commit(dict(draft_id=partial['draft_id'], expected_revision=partial['revision'],
                    confirmation_id=uuid4().hex, selections=[dict(candidate_id='c1', count=1)])))
        final = ai.imports.draft()['draft']
        self.assertEqual(final['state'], 'ready', 'Completed draft remains editable')
        self.assertEqual(final['candidates'][0]['created_count'], 3)
        self.assertEqual(final['candidates'][0]['remaining'], 0)
        self.assertEqual(final['candidates'][0]['reserved_count'], 0)
        self.assertFalse(final['candidates'][0]['ready'])
        self.assertTrue(all(op['status'] == 'finished' for op in final['operations']))
        self.assertEqual(len(controller.state()['tasks']), 3)


if __name__ == '__main__':
    unittest.main()
