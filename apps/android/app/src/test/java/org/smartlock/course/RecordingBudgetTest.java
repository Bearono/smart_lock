package org.smartlock.course;

import org.junit.Test;
import static org.junit.Assert.*;

public class RecordingBudgetTest {
    @Test public void emptyDriverStillEndsAtTenSeconds() {
        RecordingBudget budget = new RecordingBudget(50_000);
        assertTrue(budget.canRead(59_999, 0));
        assertFalse(budget.canRead(60_000, 0));
        assertFalse(budget.canRead(60_001, 0));
    }
    @Test public void fullBufferAndInvalidClockStopCapture() {
        RecordingBudget budget = new RecordingBudget(100);
        assertTrue(budget.canRead(101, 479999));
        assertFalse(budget.canRead(101, 480000));
        assertFalse(budget.canRead(99, 0));
        assertFalse(budget.canRead(101, -1));
    }
}
