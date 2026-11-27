import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { basename, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  DEFAULT_API_VERSION,
  pathForApiVersion,
  resolveApiVersion,
  resolveBuildApiVersion,
} from './apiVersionConfig';

describe('API version build configuration', () => {
  it('defaults to V1 for existing builds', () => {
    expect(resolveApiVersion()).toBe('1.0');
    expect(resolveApiVersion('  ')).toBe(DEFAULT_API_VERSION);
  });

  it('accepts a supported version and applies it to versioned or bare API paths', () => {
    expect(resolveApiVersion('2.0')).toBe('2.0');
    expect(pathForApiVersion('/v1.0/tasks', '2.0')).toBe('/v2.0/tasks');
    expect(pathForApiVersion('/tasks', '2.0')).toBe('/v2.0/tasks');
    expect(pathForApiVersion('/m8flow/tasks', '2.0')).toBe('/v2.0/m8flow/tasks');
    expect(pathForApiVersion('/v1.0foo/tasks', '2.0')).toBe('/v2.0/v1.0foo/tasks');
  });

  it('fails clearly for unsupported build versions', () => {
    expect(() => resolveApiVersion('3.0')).toThrow(/Unsupported M8Flow API version "3.0"/);
  });

  it('passes M8FLOW_API_VERSION from the repository build environment into the Vite API version', () => {
    expect(resolveBuildApiVersion({ M8FLOW_API_VERSION: '2.0' })).toBe('2.0');
    expect(resolveBuildApiVersion({ VITE_API_VERSION: '1.0', M8FLOW_API_VERSION: '2.0' })).toBe('1.0');
  });

  it('keeps API version prefixes out of executable designer request code', () => {
    const srcDirectory = resolve(dirname(fileURLToPath(import.meta.url)), '..');
    const sourceFiles: string[] = [];
    const visit = (directory: string) => {
      for (const entry of readdirSync(directory, { withFileTypes: true })) {
        const path = resolve(directory, entry.name);
        if (entry.isDirectory()) {
          visit(path);
        } else if (/\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)) {
          sourceFiles.push(path);
        }
      }
    };
    visit(srcDirectory);

    const versionRegistryFiles = new Set(['apiVersion.ts', 'apiVersionConfig.ts']);
    const hardcodedPrefixes = sourceFiles
      .filter((path) => !versionRegistryFiles.has(basename(path)))
      .flatMap((path) => {
        const contents = readFileSync(path, 'utf8');
        return /\/v\d+\.\d+\//.test(contents) ? [path] : [];
      });

    expect(hardcodedPrefixes).toEqual([]);
  });
});
