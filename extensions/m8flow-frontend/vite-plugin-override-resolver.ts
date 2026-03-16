/**
 * Vite Plugin for Override Resolution
 * 
 * This plugin enables automatic component override resolution:
 * 1. When core files import each other, check for overrides in extensions/m8flow-frontend/src
 * 2. When importing from @spiffworkflow-frontend, check for overrides first
 * 3. Bare module imports from core files resolve to extensions/m8flow-frontend/node_modules
 */

import type { Plugin } from 'vite';
import path from 'path';
import fs from 'fs';

export function overrideResolver(): Plugin {
  const extensionsDir = path.resolve(__dirname, './src');
  const coreDir = path.resolve(__dirname, '../../spiffworkflow-frontend/src');
  const localNodeModules = path.resolve(__dirname, './node_modules');

  const jsExtensions = ['.tsx', '.ts', '.jsx', '.js', '/index.tsx', '/index.ts'];
  const nonJsExtensions = ['.css', '.scss', '.sass', '.less', '.json', '.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp'];

  // Helper to check if override exists and return path
  function findOverride(relativePath: string): string | null {
    const overridePath = path.resolve(extensionsDir, relativePath);
    
    // Check if it's a non-JS file
    const isNonJsFile = nonJsExtensions.some(ext => relativePath.endsWith(ext));
    if (isNonJsFile) {
      return fs.existsSync(overridePath) ? overridePath : null;
    }

    // Check JS/TS extensions
    for (const ext of jsExtensions) {
      const testPath = overridePath.endsWith(ext) ? overridePath : overridePath + ext;
      if (fs.existsSync(testPath)) {
        return testPath;
      }
    }
    return null;
  }

  // Helper to find file in core
  function findInCore(relativePath: string): string | null {
    const corePath = path.resolve(coreDir, relativePath);
    
    const isNonJsFile = nonJsExtensions.some(ext => relativePath.endsWith(ext));
    if (isNonJsFile) {
      return fs.existsSync(corePath) ? corePath : null;
    }

    for (const ext of jsExtensions) {
      const testPath = corePath.endsWith(ext) ? corePath : corePath + ext;
      if (fs.existsSync(testPath)) {
        return testPath;
      }
    }
    return null;
  }

  return {
    name: 'override-resolver',
    enforce: 'pre',
    resolveId(source, importer, options) {
      if (!importer) return null;

      const importerInCore = importer.includes('/spiffworkflow-frontend/src/');
      const importerInExtensions = importer.includes('/extensions/m8flow-frontend/src/');

      // Handle bare module imports from spiffworkflow-frontend files
      // These need to be resolved to extensions/m8flow-frontend/node_modules
      if (importerInCore && !source.startsWith('.') && !source.startsWith('/') && !source.startsWith('@spiffworkflow-frontend')) {
        const moduleName = source.startsWith('@') 
          ? source.split('/').slice(0, 2).join('/') // @scope/package
          : source.split('/')[0]; // package
        
        const localModulePath = path.resolve(localNodeModules, moduleName);
        
        if (fs.existsSync(localModulePath)) {
          return this.resolve(source, path.resolve(extensionsDir, 'index.tsx'), { skipSelf: true });
        }
      }

      // Handle relative imports from CORE files - check for overrides
      if (importerInCore && source.startsWith('.')) {
        const importerDir = path.dirname(importer);
        const resolvedCorePath = path.resolve(importerDir, source);
        
        // Get the relative path from core src directory
        const relativePath = path.relative(coreDir, resolvedCorePath);
        
        // Don't process if it resolves outside of core src
        if (relativePath.startsWith('..')) {
          return null;
        }

        // Check if override exists
        const overridePath = findOverride(relativePath);
        if (overridePath) {
          return overridePath;
        }

        // No override, let Vite resolve normally
        return null;
      }

      // Handle relative imports from EXTENSIONS files
      if (importerInExtensions && source.startsWith('.')) {
        const importerDir = path.dirname(importer);
        const resolvedPath = path.resolve(importerDir, source);

        // Check if resolved path is within extensions/m8flow-frontend/src
        if (resolvedPath.startsWith(extensionsDir)) {
          // Get relative path from extensions src
          const relativePath = path.relative(extensionsDir, resolvedPath);

          // Check if local override exists
          const overridePath = findOverride(relativePath);
          if (overridePath) {
            return overridePath;
          }

          // Fallback to core
          const corePath = findInCore(relativePath);
          if (corePath) {
            return corePath;
          }
        }
      }

      // Handle @spiffworkflow-frontend imports (from any file)
      if (source.startsWith('@spiffworkflow-frontend')) {
        const modulePath = source.replace('@spiffworkflow-frontend', '');
        const cleanPath = modulePath.startsWith('/') ? modulePath.slice(1) : modulePath;

        // Check for override first
        const overridePath = findOverride(cleanPath);
        if (overridePath) {
          return overridePath;
        }

        // No override - return null to let Vite's alias handle it
        return null;
      }

      return null;
    },
  };
}
