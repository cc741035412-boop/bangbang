import unittest
from unittest.mock import patch, Mock
import person_service as people


class PersonGroupingTest(unittest.TestCase):
    def test_aliases_and_known_names_and_group_are_separate(self):
        result = people.identify_people('测试幼儿甲在旁。幼儿A穿红衣。幼儿B穿蓝衣。幼儿A搭建。三个孩子围观。', ['测试幼儿甲'])
        self.assertEqual([g['ref_indexes'] for g in result['people']], [[0, 2], [1]])
        self.assertTrue(result['refs'][3]['group'])
        self.assertIn('红衣', result['people'][0]['clues'][0])

    def test_model_groups_repeated_mentions_without_sending_names(self):
        response = Mock()
        response.json.return_value = {'choices': [{'message': {'content': '{"people":[{"ref_indexes":[0,2]},{"ref_indexes":[1]}]}'}}]}
        with patch.object(people.ai_service, 'AI_MODE', 'deepseek'), patch.object(people.ai_service, 'DEEPSEEK_API_KEY', 'test-only'), patch.object(people.ai_service.httpx, 'post', return_value=response) as post:
            result = people.identify_people('测试甲在旁。穿红衣的男孩搭建。女孩递积木。男孩接过积木。', ['测试甲'])
        self.assertEqual(result['method'], 'ai')
        self.assertEqual(result['people'][0]['ref_indexes'], [0, 2])
        self.assertNotIn('测试甲', post.call_args.kwargs['json']['messages'][0]['content'])

    def test_invalid_alias_groups_rejected(self):
        refs = people.references('幼儿A搭建。幼儿B观察。幼儿A转身。', [])
        for value in [[{'ref_indexes': [0, 1, 2]}], [{'ref_indexes': [0, 2]}], [{'ref_indexes': [0, 2]}, {'ref_indexes': [1, 1]}]]:
            with self.assertRaises(ValueError):
                people.validate_groups(value, refs)
