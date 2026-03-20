"""
PDF Exporter Service
Generates PDF files from schedule data for individual blocks or full programs.
"""

from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from datetime import datetime
import io

class SchedulePDFExporter:
    """Generate PDF exports of schedule blocks."""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Setup custom paragraph styles for PDF."""
        self.styles.add(ParagraphStyle(
            name='BlockTitle',
            parent=self.styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#1F2937'),
            spaceAfter=12,
            fontName='Helvetica-Bold'
        ))
        
        self.styles.add(ParagraphStyle(
            name='BlockInfo',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#6B7280'),
            spaceAfter=6
        ))
    
    def export_block_to_pdf(self, block, term_courses, program_name):
        """
        Export a single block's schedule to PDF.
        
        Args:
            block: Block instance
            term_courses: List of TermCourse objects
            program_name: Name of the program
            
        Returns:
            BytesIO object containing PDF data
        """
        buffer = io.BytesIO()
        
        # Create PDF with landscape orientation for better timetable display
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(letter),
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch,
            title=f"{program_name} - {block.block_name}"
        )
        
        story = []
        
        # Header
        story.append(Paragraph(
            f"{program_name} Engineering - {block.block_name}",
            self.styles['BlockTitle']
        ))
        
        # Block Info
        info_text = f"<b>Block Size:</b> {block.size} students | <b>Generated:</b> {datetime.now().strftime('%B %d, %Y')}"
        story.append(Paragraph(info_text, self.styles['BlockInfo']))
        story.append(Spacer(1, 0.2*inch))
        
        # Timetable
        if term_courses:
            story.append(self._build_timetable_table(term_courses))
        else:
            story.append(Paragraph("No courses scheduled for this block.", self.styles['Normal']))
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        return buffer
    
    def export_program_to_pdf(self, program, blocks_data):
        """
        Export entire program schedule to PDF.
        
        Args:
            program: Program instance
            blocks_data: List of dicts with block and courses info
            
        Returns:
            BytesIO object containing PDF data
        """
        buffer = io.BytesIO()
        
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(letter),
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch,
            title=f"{program.program_name} Schedule"
        )
        
        story = []
        
        # Cover page
        story.append(Paragraph(
            f"{program.program_name} Engineering - First Year Schedule",
            self.styles['BlockTitle']
        ))
        
        program_info = f"""
        <b>Program:</b> {program.program_name}<br/>
        <b>Students Enrolled:</b> {program.enrolled or 0}<br/>
        <b>Total Blocks:</b> {len(blocks_data)}<br/>
        <b>Generated:</b> {datetime.now().strftime('%B %d, %Y at %I:%M %p')}
        """
        story.append(Paragraph(program_info, self.styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        # Add each block on a new page
        for idx, block_info in enumerate(blocks_data):
            if idx > 0:
                story.append(PageBreak())
            
            block = block_info['block']
            story.append(Paragraph(
                f"Block: {block.block_name}",
                self.styles['BlockTitle']
            ))
            
            block_details = f"<b>Size:</b> {block.size} students | <b>Ranking:</b> {block.ranking or 'N/A'}/100"
            story.append(Paragraph(block_details, self.styles['BlockInfo']))
            story.append(Spacer(1, 0.15*inch))
            
            # Add timetable for this block
            courses = block_info.get('courses', [])
            if courses:
                story.append(self._build_timetable_table(courses))
            else:
                story.append(Paragraph("No courses scheduled.", self.styles['Normal']))
        
        doc.build(story)
        buffer.seek(0)
        return buffer
    
    def _build_timetable_table(self, courses):
        """
        Build a formatted timetable table from courses.
        
        Args:
            courses: List of course dicts with code, section, type, days, times
            
        Returns:
            Table object
        """
        data = [
            ['Course Code', 'Section', 'Type', 'Days', 'Time', 'Enrollment']
        ]
        
        for course in courses:
            time_str = f"{course.get('start_time', '—')} – {course.get('end_time', '—')}"
            enrollment = f"{course.get('enrolled', 0)}/{course.get('capacity', 0)}"
            
            data.append([
                course.get('code', ''),
                course.get('section', ''),
                course.get('type', ''),
                course.get('days', ''),
                time_str,
                enrollment
            ])
        
        table = Table(data, colWidths=[1.2*inch, 0.8*inch, 0.8*inch, 1*inch, 1.2*inch, 1*inch])
        
        table.setStyle(TableStyle([
            # Header styling
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F2937')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            
            # Body styling
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9FAFB')]),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E5E7EB')),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        
        return table