from m8flow_backend.integrations.auth.keycloak.claims import memberships_from_organization_claim


def test_organization_claim_preserves_directory_group_for_workflow_lanes():
    memberships = memberships_from_organization_claim(
        {
            "organization": {
                "m8flow": {
                    "id": "tenant-1",
                    "groups": ["/Submitters"],
                }
            }
        }
    )

    assert memberships[0].roles == ["submitter"]
    assert memberships[0].groups == ["Submitters"]
