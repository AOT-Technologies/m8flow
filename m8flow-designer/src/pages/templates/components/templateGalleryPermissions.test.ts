import { describe, expect, it } from 'vitest';

import type { Template } from '@/lib/templatesApi';
import {
  canDeleteGalleryTemplate,
  canRestoreGalleryTemplate,
  deleteDisabledReason,
} from './templateGalleryPermissions';

const draft: Template = {
  id: 1,
  templateKey: 'invoice',
  version: 'V1',
  name: 'Invoice',
  description: null,
  tags: null,
  category: null,
  tenantId: 't1',
  visibility: 'TENANT',
  files: [],
  isPublished: false,
  status: 'draft',
  createdBy: 'editor',
  modifiedBy: 'editor',
  createdAtInSeconds: 1,
  updatedAtInSeconds: 1,
};

const published: Template = { ...draft, isPublished: true, status: 'published' };

describe('templateGalleryPermissions', () => {
  it('lets a tenant-admin delete published and restore', () => {
    const admin = { isSuperAdmin: false, canManageTenant: true, currentUsername: 'admin' };
    expect(canDeleteGalleryTemplate(published, admin)).toBe(true);
    expect(canDeleteGalleryTemplate(draft, admin)).toBe(true);
    expect(canRestoreGalleryTemplate(admin)).toBe(true);
  });

  it('lets an editor hard-delete their own draft but not a published template', () => {
    const editor = { isSuperAdmin: false, canManageTenant: false, currentUsername: 'editor' };
    expect(canDeleteGalleryTemplate(draft, editor)).toBe(true);
    expect(canDeleteGalleryTemplate(published, editor)).toBe(false);
    expect(deleteDisabledReason(published, editor)).toMatch(/published/);
    expect(canRestoreGalleryTemplate(editor)).toBe(false);
  });

  it('blocks super-admin delete and restore', () => {
    const superAdmin = { isSuperAdmin: true, canManageTenant: true, currentUsername: 'platform' };
    expect(canDeleteGalleryTemplate(published, superAdmin)).toBe(false);
    expect(canRestoreGalleryTemplate(superAdmin)).toBe(false);
  });
});
