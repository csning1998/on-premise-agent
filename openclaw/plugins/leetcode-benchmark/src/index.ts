import { Type } from '@sinclair/typebox';
import { defineToolPlugin } from 'openclaw/plugin-sdk/tool-plugin';

const PROBLEMS: Record<number, { title: string; difficulty: string; tags: string[] }> = {
    1: { title: 'Two Sum', difficulty: 'Easy', tags: ['Array', 'Hash Table'] },
    4: {
        title: 'Median of Two Sorted Arrays',
        difficulty: 'Hard',
        tags: ['Array', 'Binary Search'],
    },
    20: {
        title: 'Valid Parentheses',
        difficulty: 'Easy',
        tags: ['Stack', 'String'],
    },
    42: {
        title: 'Trapping Rain Water',
        difficulty: 'Hard',
        tags: ['Array', 'Two Pointers', 'Stack'],
    },
    200: {
        title: 'Number of Islands',
        difficulty: 'Medium',
        tags: ['Array', 'DFS', 'BFS', 'Union Find'],
    },
};

export default defineToolPlugin({
    id: 'leetcode-benchmark',
    name: 'LeetCode Benchmark',
    description: 'Look up a fixed local table of LeetCode problems for tool-calling benchmarking.',
    tools: (tool) => [
        tool({
            name: 'lookup_leetcode_problem',
            description:
                'Look up a LeetCode problem by its numeric ID and return its title, difficulty, and tags.',
            parameters: Type.Object({
                problem_id: Type.Integer({
                    description: 'LeetCode problem number, e.g. 1.',
                }),
            }),
            execute: async ({ problem_id }) => {
                const problem = PROBLEMS[problem_id];
                if (!problem) {
                    return { found: false, problem_id };
                }
                return { found: true, problem_id, ...problem };
            },
        }),
    ],
});
