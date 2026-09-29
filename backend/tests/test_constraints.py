#!/usr/bin/env python3
"""
Simple constraint test using raw SQL.
Tests the partial unique index on workflow_runs.
"""
import psycopg
from app.config import settings

def test_partial_unique_constraint():
    """Test the partial unique index on workflow_runs using raw SQL"""
    
    # Parse DATABASE_URL
    db_url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    
    conn = psycopg.connect(db_url)
    cur = conn.cursor()
    
    try:
        # Create test data
        cur.execute("""
            INSERT INTO content_strategies (id, name, description, config, enabled)
            VALUES (gen_random_uuid(), 'Test Strategy', 'For constraint testing', '{}', true)
            RETURNING id
        """)
        strategy_id = cur.fetchone()[0]
        print(f"✓ Created strategy {strategy_id}")
        
        cur.execute("""
            INSERT INTO ideas (id, strategy_id, title, status, scoring_metadata)
            VALUES (gen_random_uuid(), %s, 'Test Idea', 'SELECTED', '{}')
            RETURNING id
        """, (strategy_id,))
        idea_id = cur.fetchone()[0]
        print(f"✓ Created idea {idea_id}")
        
        # Test 1: Insert first RUNNING workflow_run (should succeed)
        cur.execute("""
            INSERT INTO workflow_runs (id, idea_id, strategy_id, status, run_metadata)
            VALUES (gen_random_uuid(), %s, %s, 'RUNNING', '{}')
            RETURNING id, status
        """, (idea_id, strategy_id))
        run1_id, run1_status = cur.fetchone()
        conn.commit()
        print(f"✓ Test 1 PASSED: Inserted first RUNNING workflow_run {run1_id}")
        
        # Test 2: Attempt second PAUSED workflow_run for same idea (should fail)
        try:
            cur.execute("""
                INSERT INTO workflow_runs (id, idea_id, strategy_id, status, run_metadata)
                VALUES (gen_random_uuid(), %s, %s, 'PAUSED', '{}')
            """, (idea_id, strategy_id))
            conn.commit()
            print("✗ Test 2 FAILED: Second active workflow_run was allowed (constraint not working!)")
            return False
        except psycopg.errors.UniqueViolation as e:
            conn.rollback()
            print(f"✓ Test 2 PASSED: Second PAUSED workflow_run was rejected")
            print(f"  Error: {str(e).splitlines()[0]}")
        
        # Test 3: Insert FAILED workflow_run for same idea (should succeed - terminal status)
        cur.execute("""
            INSERT INTO workflow_runs (id, idea_id, strategy_id, status, run_metadata)
            VALUES (gen_random_uuid(), %s, %s, 'FAILED', '{}')
            RETURNING id, status
        """, (idea_id, strategy_id))
        run3_id, run3_status = cur.fetchone()
        conn.commit()
        print(f"✓ Test 3 PASSED: Inserted FAILED workflow_run {run3_id} (terminal status allowed)")
        
        # Cleanup
        cur.execute("DELETE FROM workflow_runs WHERE idea_id = %s", (idea_id,))
        cur.execute("DELETE FROM ideas WHERE id = %s", (idea_id,))
        cur.execute("DELETE FROM content_strategies WHERE id = %s", (strategy_id,))
        conn.commit()
        print("\n✓ All constraint tests PASSED")
        print(f"✓ Cleanup completed")
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    success = test_partial_unique_constraint()
    exit(0 if success else 1)
