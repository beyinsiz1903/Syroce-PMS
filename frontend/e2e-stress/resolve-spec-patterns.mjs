#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const SPEC_ROOT = 'e2e-stress/specs/';
const SAFE_PATTERN = /^e2e-stress\/specs\/[A-Za-z0-9_./*-]+\.spec\.js$/;

function walkFiles(directory, relativeRoot = '') {
    return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
        const relativePath = path.posix.join(relativeRoot, entry.name);
        const absolutePath = path.join(directory, entry.name);
        return entry.isDirectory() ? walkFiles(absolutePath, relativePath) : [relativePath];
    });
}

function globToRegExp(pattern) {
    const escaped = pattern.replace(/[.+?^${}()|[\]\\]/g, '\\$&');
    return new RegExp(`^${escaped.replaceAll('*', '[^/]*')}$`);
}

export function resolveSpecPatterns(patterns, { cwd = process.cwd() } = {}) {
    if (!Array.isArray(patterns) || patterns.length === 0) {
        throw new Error('BLOCKED_TEST_DISCOVERY: no spec patterns were provided');
    }

    const specDirectory = path.join(cwd, 'e2e-stress', 'specs');
    const availableFiles = walkFiles(specDirectory)
        .map((file) => `${SPEC_ROOT}${file}`)
        .sort();
    const resolved = [];
    const seen = new Set();

    for (const pattern of patterns) {
        if (!SAFE_PATTERN.test(pattern) || pattern.includes('..')) {
            throw new Error(`BLOCKED_TEST_DISCOVERY: unsafe spec pattern: ${pattern}`);
        }

        const matcher = globToRegExp(pattern);
        const matches = availableFiles.filter((file) => matcher.test(file));
        if (matches.length === 0) {
            throw new Error(`BLOCKED_TEST_DISCOVERY: pattern matched zero files: ${pattern}`);
        }

        for (const match of matches) {
            if (!seen.has(match)) {
                resolved.push(match);
                seen.add(match);
            }
        }
    }

    if (resolved.length === 0) {
        throw new Error('BLOCKED_TEST_DISCOVERY: resolved spec count is zero');
    }
    return resolved;
}

const invokedDirectly = process.argv[1]
    && pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url;

if (invokedDirectly) {
    try {
        for (const file of resolveSpecPatterns(process.argv.slice(2))) {
            process.stdout.write(`${file}\n`);
        }
    } catch (error) {
        process.stderr.write(`${error.message}\n`);
        process.exitCode = 2;
    }
}
