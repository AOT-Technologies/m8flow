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
  createdAt: new Date(1000).toISOString(),
  updatedAt: new Date(1000).toISOString(),
};

const published: Template = { ...draft, isPublished: true, status: 'published' };

describe('templateGalleryPermissions', () => {
  it('lets a tenant-admin delete published and restore', () => {
    const admin = { isSuperAdmin: false, canManageTenant: true, currentUsername: 'admin', activeTenantId: 't1' };
    expect(canDeleteGalleryTemplate(published, admin)).toBe(true);
    expect(canDeleteGalleryTemplate(draft, admin)).toBe(true);
    expect(canRestoreGalleryTemplate(published, admin)).toBe(true);
  });

  it('lets an editor hard-delete their own draft but not a published template', () => {
    const editor = { isSuperAdmin: false, canManageTenant: false, currentUsername: 'editor', activeTenantId: 't1' };
    expect(canDeleteGalleryTemplate(draft, editor)).toBe(true);
    expect(canDeleteGalleryTemplate(published, editor)).toBe(false);
    expect(deleteDisabledReason(published, editor)).toMatch(/published/);
    expect(canRestoreGalleryTemplate(published, editor)).toBe(false);
  });

  it('lets the creator delete and restore their own published private template', () => {
    const editor = { isSuperAdmin: false, canManageTenant: false, currentUsername: 'editor', activeTenantId: 't1' };
    const otherEditor = { ...editor, currentUsername: 'other' };
    const privatePublished: Template = { ...published, visibility: 'PRIVATE' };
    expect(canDeleteGalleryTemplate(privatePublished, editor)).toBe(true);
    expect(deleteDisabledReason(privatePublished, editor)).toBe('');
    expect(canRestoreGalleryTemplate(privatePublished, editor)).toBe(true);
    expect(canDeleteGalleryTemplate(privatePublished, otherEditor)).toBe(false);
    expect(canRestoreGalleryTemplate(privatePublished, otherEditor)).toBe(false);
  });

  it('keeps another tenant\'s public template read-only for a tenant-admin and its creator', () => {
    const otherTenantAdmin = { isSuperAdmin: false, canManageTenant: true, currentUsername: 'admin', activeTenantId: 't2' };
    const creatorInOtherTenant = { isSuperAdmin: false, canManageTenant: false, currentUsername: 'editor', activeTenantId: 't2' };
    const publicPublished: Template = { ...published, visibility: 'PUBLIC' };
    const publicDraft: Template = { ...draft, visibility: 'PUBLIC' };
    for (const actor of [otherTenantAdmin, creatorInOtherTenant]) {
      expect(canDeleteGalleryTemplate(publicPublished, actor)).toBe(false);
      expect(canDeleteGalleryTemplate(publicDraft, actor)).toBe(false);
      expect(canRestoreGalleryTemplate(publicPublished, actor)).toBe(false);
      expect(deleteDisabledReason(publicPublished, actor)).toMatch(/another tenant/);
    }
  });

  it('blocks super-admin delete and restore', () => {
    const superAdmin = { isSuperAdmin: true, canManageTenant: true, currentUsername: 'platform', activeTenantId: 't1' };
    expect(canDeleteGalleryTemplate(published, superAdmin)).toBe(false);
    expect(canRestoreGalleryTemplate(published, superAdmin)).toBe(false);
  });
});
